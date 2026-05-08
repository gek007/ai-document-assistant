import json
import os
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from src.agent.schemas import TOOL_SCHEMAS
from src.agent.tools import TOOL_REGISTRY
from src.document_store import DocumentStore
from src.models import StreamEvent, TraceStep

SYSTEM_PROMPT = """You are a Document Agent — an AI assistant that helps users understand and analyze a collection of documents.

You have access to the following tools:
- list_documents: Always call this first to see what files are available
- read_document: Read the full content of markdown, text, log, and JSON files
- search_in_document: Find specific text within a document without reading the whole file
- parse_csv: Analyze CSV files — always use this instead of read_document for CSV files
- query_json: Extract specific values from JSON files by dot-path

Guidelines:
- Always start by calling list_documents to know what is available
- For CSV files, call parse_csv — it surfaces data quality issues automatically
- For cross-document questions, gather all relevant documents before synthesizing your answer
- Be explicit about data inconsistencies or quality issues you find — never hide them
- State your assumption clearly when a question is ambiguous
- If a file is not found or a tool returns an error, report it and continue where possible
"""


async def run_agent_stream(
    user_message: str,
    history: list[dict],
    store: DocumentStore,
    model: str | None = None,
    max_iterations: int | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
    max_iterations = max_iterations or int(os.environ.get("MAX_AGENT_ITERATIONS", "10"))

    messages: list[dict] = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_message}]
    )
    trace: list[TraceStep] = []

    for iteration in range(max_iterations):
        accumulated_content = ""
        accumulated_tool_calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            stream=True,
        )

        async for chunk in stream:
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

        # ── Final answer ───────────────────────────────────────────────────────
        if finish_reason == "stop" or (not accumulated_tool_calls and accumulated_content):
            messages.append({"role": "assistant", "content": accumulated_content})
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

                yield StreamEvent(
                    type="tool_start",
                    content=f"Calling `{tool_name}`" + (f" → {args}" if args else ""),
                    trace=trace,
                )

                try:
                    result = await TOOL_REGISTRY[tool_name](store, **args)
                except KeyError:
                    result = f"Error: unknown tool '{tool_name}'"
                except Exception as e:
                    result = f"Error executing {tool_name}: {e}"

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

    yield StreamEvent(
        type="error",
        content=f"Agent reached the maximum of {max_iterations} iterations without a final answer.",
        trace=trace,
    )
