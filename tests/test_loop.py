import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.loop import run_agent_stream
from src.document_store import DocumentStore
from src.models import StreamEvent

pytestmark = pytest.mark.asyncio


# ── Mock chunk builders ────────────────────────────────────────────────────────

def _choice(content=None, tool_calls=None, finish_reason=None):
    choice = MagicMock()
    choice.delta.content = content
    choice.delta.tool_calls = tool_calls
    choice.finish_reason = finish_reason
    return choice


def content_chunk(text: str, finish_reason: str | None = None):
    chunk = MagicMock()
    chunk.choices = [_choice(content=text, finish_reason=finish_reason)]
    return chunk


def tool_call_chunk(index: int, tool_id: str, name: str, arguments: str, finish_reason: str | None = None):
    tc = MagicMock()
    tc.index = index
    tc.id = tool_id
    tc.function.name = name
    tc.function.arguments = arguments
    chunk = MagicMock()
    chunk.choices = [_choice(tool_calls=[tc], finish_reason=finish_reason)]
    return chunk


def finish_chunk(finish_reason: str):
    chunk = MagicMock()
    chunk.choices = [_choice(finish_reason=finish_reason)]
    return chunk


async def _async_stream(chunks):
    for chunk in chunks:
        yield chunk


def make_mock_client(calls: list[list]) -> MagicMock:
    """Build a mock AsyncOpenAI client that returns different chunk sequences per call."""
    call_iter = iter(calls)

    async def _create(**kwargs):
        return _async_stream(next(call_iter))

    client = MagicMock()
    client.chat.completions.create = _create
    return client


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_docs_dir: Path) -> DocumentStore:
    return DocumentStore(str(tmp_docs_dir))


# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_single_turn_no_tool_calls(store: DocumentStore):
    chunks = [
        content_chunk("Hello"),
        content_chunk(" there"),
        content_chunk("!", finish_reason="stop"),
    ]
    mock_client = make_mock_client([chunks])

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("Hi", [], store)]

    types = [e.type for e in events]
    assert "content_delta" in types
    assert types[-1] == "done"

    done_event = events[-1]
    assert done_event.content == "Hello there!"
    assert done_event.trace == []


async def test_single_tool_call_then_answer(store: DocumentStore):
    tool_chunks = [
        tool_call_chunk(0, "call_1", "list_documents", "{}"),
        finish_chunk("tool_calls"),
    ]
    answer_chunks = [
        content_chunk("You have 5 documents.", finish_reason="stop"),
    ]
    mock_client = make_mock_client([tool_chunks, answer_chunks])

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("What files?", [], store)]

    types = [e.type for e in events]
    assert "tool_start" in types
    assert "tool_end" in types
    assert types[-1] == "done"

    done_event = events[-1]
    assert len(done_event.trace) == 1
    assert done_event.trace[0].tool == "list_documents"


async def test_chained_tool_calls_build_trace(store: DocumentStore):
    list_chunks = [
        tool_call_chunk(0, "call_1", "list_documents", "{}", finish_reason="tool_calls"),
    ]
    read_chunks = [
        tool_call_chunk(0, "call_2", "read_document", '{"filename": "config.json"}', finish_reason="tool_calls"),
    ]
    answer_chunks = [
        content_chunk("Config loaded.", finish_reason="stop"),
    ]
    mock_client = make_mock_client([list_chunks, read_chunks, answer_chunks])

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("Read the config", [], store)]

    done_event = events[-1]
    assert done_event.type == "done"
    assert len(done_event.trace) == 2
    assert done_event.trace[0].tool == "list_documents"
    assert done_event.trace[1].tool == "read_document"


async def test_tool_result_is_truncated_in_trace(store: DocumentStore):
    chunks = [
        tool_call_chunk(0, "call_1", "read_document", '{"filename": "meetings.md"}', finish_reason="tool_calls"),
    ]
    answer_chunks = [content_chunk("Done.", finish_reason="stop")]
    mock_client = make_mock_client([chunks, answer_chunks])

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("Read meetings", [], store)]

    done_event = events[-1]
    assert len(done_event.trace[0].output) <= 303  # 300 chars + "..."


async def test_unknown_tool_surfaces_error_and_continues(store: DocumentStore):
    chunks = [
        tool_call_chunk(0, "call_1", "nonexistent_tool", "{}", finish_reason="tool_calls"),
    ]
    answer_chunks = [content_chunk("Could not complete.", finish_reason="stop")]
    mock_client = make_mock_client([chunks, answer_chunks])

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("Do something", [], store)]

    # Loop should continue and reach "done" despite the unknown tool
    assert events[-1].type == "done"
    tool_end = next(e for e in events if e.type == "tool_end")
    assert tool_end is not None


async def test_max_iterations_yields_error(store: DocumentStore):
    # Always return tool calls — never a final answer
    tool_chunks = [
        tool_call_chunk(0, "call_x", "list_documents", "{}", finish_reason="tool_calls"),
    ]
    mock_client = make_mock_client([tool_chunks] * 20)

    with patch("src.agent.loop.AsyncOpenAI", return_value=mock_client):
        events = [e async for e in run_agent_stream("Loop forever", [], store, max_iterations=2)]

    assert events[-1].type == "error"
    assert "maximum" in events[-1].content


async def test_history_is_included_in_messages(store: DocumentStore):
    captured_messages = []

    async def _create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return _async_stream([content_chunk("Done.", finish_reason="stop")])

    client = MagicMock()
    client.chat.completions.create = _create

    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]

    with patch("src.agent.loop.AsyncOpenAI", return_value=client):
        events = [e async for e in run_agent_stream("New question", history, store)]

    roles = [m["role"] for m in captured_messages]
    assert roles[0] == "system"
    assert "user" in roles
    assert "assistant" in roles
    # History messages appear before the new user message
    assert captured_messages[-1]["content"] == "New question"
