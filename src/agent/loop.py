import json
import os
import uuid
from collections.abc import AsyncGenerator

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.schemas import TOOL_SCHEMAS
from src.agent.tools import TOOL_REGISTRY
from src.document_store import DocumentStore
from src.logger import get_logger
from src.models import StreamEvent, TraceStep

log = get_logger(__name__)

_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


_STORE_TRACES = os.environ.get("OPENAI_STORE_TRACES", "true").lower() == "true"


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _call_openai(client: AsyncOpenAI, **kwargs):
    log.debug(
        "LLM call: model=%s, messages=%d, tools=%d, store=%s",
        kwargs.get("model"),
        len(kwargs.get("messages", [])),
        len(kwargs.get("tools", [])),
        kwargs.get("store"),
    )
    return await client.chat.completions.create(**kwargs)


async def run_agent_stream(
    user_message: str,
    history: list[dict],
    store: DocumentStore,
    model: str | None = None,
    max_iterations: int | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    raw_project = os.environ.get("OPENAI_PROJECT_ID", "")
    project_id = raw_project if raw_project.startswith("proj_") else None

    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        project=project_id,
    )
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
    max_iterations = max_iterations or int(os.environ.get("MAX_AGENT_ITERATIONS", "10"))
    store_traces = _STORE_TRACES
    session_id = str(uuid.uuid4())

    log.info(
        "Agent started: model=%s, max_iterations=%d, history_turns=%d, session_id=%s, store_traces=%s, project=%s",
        model, max_iterations, len(history) // 2, session_id, store_traces,
        project_id or "none",
    )

    messages: list[dict] = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    trace: list[TraceStep] = []

    for iteration in range(max_iterations):
        log.debug("Agent iteration %d/%d, messages=%d", iteration + 1, max_iterations, len(messages))

        accumulated_content = ""
        accumulated_tool_calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        completion_id: str | None = None

        try:
            stream = await _call_openai(
                client,
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                stream=True,
                store=store_traces,
                metadata={
                    "app": "ai-document-assistant",
                    "session_id": session_id,
                    "iteration": str(iteration + 1),
                },
            )
        except _RETRYABLE as e:
            log.error("LLM API error after retries: %s", e)
            yield StreamEvent(type="error", content=f"LLM API error: {e}", trace=trace)
            return
        except Exception as e:
            log.error("Unexpected LLM error: %s: %s", type(e).__name__, e)
            yield StreamEvent(type="error", content=f"{type(e).__name__}: {e}", trace=trace)
            return

        async for chunk in stream:
            if completion_id is None and chunk.id:
                completion_id = chunk.id
                log.debug(
                    "LLM completion_id=%s (view at platform.openai.com/traces/%s)",
                    completion_id, completion_id,
                )
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta

            if delta.content:
                accumulated_content += delta.content
                yield StreamEvent(type="content_delta", content=delta.content, trace=trace)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        accumulated_tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        accumulated_tool_calls[idx]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

        log.debug(
            "LLM response: finish_reason=%s, content_len=%d, tool_calls=%d",
            finish_reason, len(accumulated_content), len(accumulated_tool_calls),
        )

        # ── Final answer ───────────────────────────────────────────────────────
        if finish_reason == "stop" or (not accumulated_tool_calls and accumulated_content):
            messages.append({"role": "assistant", "content": accumulated_content})
            log.info(
                "Agent done in %d iteration(s), trace_steps=%d, answer_len=%d, completion_id=%s",
                iteration + 1, len(trace), len(accumulated_content), completion_id,
            )
            yield StreamEvent(type="done", content=accumulated_content, trace=trace)
            return

        # ── Tool calls ─────────────────────────────────────────────────────────
        if accumulated_tool_calls:
            tool_calls_payload = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in accumulated_tool_calls.values()
            ]
            messages.append({
                "role": "assistant",
                "content": accumulated_content or None,
                "tool_calls": tool_calls_payload,
            })

            for tc in accumulated_tool_calls.values():
                tool_name = tc["name"]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}

                log.info("Tool call: %s(%s)", tool_name, json.dumps(args))
                yield StreamEvent(
                    type="tool_start",
                    content=f"Calling `{tool_name}`" + (f" → {args}" if args else ""),
                    trace=trace,
                )

                try:
                    result = await TOOL_REGISTRY[tool_name](store, **args)
                except KeyError:
                    result = f"Error: unknown tool '{tool_name}'"
                    log.warning("Unknown tool requested: %s", tool_name)
                except Exception as e:
                    result = f"Error executing {tool_name}: {e}"
                    log.error("Tool %s raised: %s", tool_name, e)

                log.debug("Tool %s result (first 200): %s", tool_name, result[:200])

                trace.append(TraceStep(
                    tool=tool_name,
                    input=args,
                    output=result[:300] + ("..." if len(result) > 300 else ""),
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

                yield StreamEvent(
                    type="tool_end",
                    content=f"`{tool_name}` done",
                    trace=trace,
                )

    log.warning("Agent hit max_iterations=%d without final answer", max_iterations)
    yield StreamEvent(
        type="error",
        content=f"Agent reached the maximum of {max_iterations} iterations without a final answer.",
        trace=trace,
    )
