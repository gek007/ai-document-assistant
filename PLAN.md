# AI-Document-Assistant — Implementation Plan

## Context

A Document Agent where users ask natural language questions about a collection of documents. The agent loop is hand-rolled (no LangChain/CrewAI/etc.), using OpenAI's function-calling API with async streaming. UI is Gradio 6. Documents live in a folder configured via `.env`. Logging, retry, and OpenAI platform traces are built in.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Package manager | `uv` + `pyproject.toml` |
| LLM | OpenAI `gpt-4o` — async streaming + function calling |
| UI | Gradio 6.x (`gr.Blocks`) |
| Async file I/O | `aiofiles>=23.0` |
| Config | `python-dotenv` |
| Retry | `tenacity>=8.0` |
| Testing | `pytest` + `pytest-asyncio` |

---

## Directory Structure

```
ai-document-assistant/
├── documents/                   # Live document folder (path via .env)
│   ├── meetings.md
│   ├── sales-q1.csv
│   ├── emails.txt
│   ├── config.json
│   └── server-log.txt
│
├── src/
│   ├── __init__.py
│   ├── logger.py                # Logging setup: TRACE level, rotating file handler
│   ├── models.py                # Pydantic models: TraceStep, StreamEvent
│   ├── document_store.py        # Async file I/O with path guard + retry
│   └── agent/
│       ├── __init__.py
│       ├── helpers.py           # is_numeric() utility
│       ├── schemas.py           # OpenAI tool schemas (TOOL_SCHEMAS)
│       ├── tools.py             # 5 async tool implementations + TOOL_REGISTRY
│       └── loop.py              # Async streaming agent loop
│
├── app/
│   ├── __init__.py
│   └── ui.py                    # Gradio 6 layout + streaming event handlers
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # tmp_docs_dir fixture
│   ├── test_document_store.py   # 10 tests
│   ├── test_tools.py            # 20 tests
│   └── test_loop.py             # 7 tests
│
├── main.py                      # Entry point: load .env → logging → Gradio
├── pyproject.toml
├── .env / .env.example
├── PLAN.md
├── IMPLEMENTATION_ORDER.md
└── README.md
```

---

## Configuration (`.env`)

```
# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o
OPENAI_PROJECT_ID=proj_your_project_id_here   # groups traces on platform.openai.com

# Documents
DOCUMENTS_DIR=./documents
MAX_AGENT_ITERATIONS=10
MAX_FILE_SIZE_KB=100

# OpenAI traces (visible at platform.openai.com → Traces)
OPENAI_STORE_TRACES=true

# Logging
LOG_LEVEL=INFO          # TRACE | DEBUG | INFO | WARNING | ERROR
LOG_DIR=./logs
LOG_MAX_FILES=10
LOG_MAX_SIZE_MB=10
```

---

## Core Modules

### `src/logger.py`

- Adds custom `TRACE` level (level 5, below `DEBUG`)
- `setup_logging()` — reads env vars, sets up console + `RotatingFileHandler`
  - `backupCount = LOG_MAX_FILES - 1` → total on-disk files = `LOG_MAX_FILES`
- `get_logger(name)` — returns a named logger for each module

### `src/document_store.py`

Async filesystem abstraction. All file access goes through here.

- `list_files()` — `asyncio.to_thread(os.scandir)`, always current
- `read_file(filename)` — `aiofiles` read, path traversal guard, size truncation
- `save_file(filename, content)` — `aiofiles` write, path guard
- `delete_file(filename)` — `asyncio.to_thread(path.unlink)`, path guard
- `file_exists(filename)` — sync check wrapped safely
- **Retry**: `@tenacity.retry` on all file ops — retries transient `OSError` (not `FileNotFoundError`/`PermissionError`), 3 attempts, 0.5s fixed wait
- **Path guard**: resolves both paths and checks prefix + `os.sep` to prevent traversal
- `get_store()` — singleton factory, reads `DOCUMENTS_DIR` + `MAX_FILE_SIZE_KB` from env

### `src/models.py`

```python
class TraceStep(BaseModel):
    tool: str
    input: dict
    output: str          # truncated to 300 chars

class StreamEvent(BaseModel):
    type: Literal["tool_start", "tool_end", "content_delta", "done", "error"]
    content: str = ""
    trace: list[TraceStep] = []
```

### `src/agent/schemas.py`

`TOOL_SCHEMAS` — list of 5 OpenAI function-calling schema dicts passed as `tools=` to the API.

### `src/agent/helpers.py`

`is_numeric(value)` — checks if a string is a valid number (used in CSV quality detection).

### `src/agent/tools.py`

Five async tool implementations, all taking `store: DocumentStore` as first arg:

| Tool | Key behaviour |
|---|---|
| `list_documents` | Markdown table: name / size / type / modified |
| `read_document` | Full file content; returns error string on failure |
| `search_in_document` | Case-insensitive line search with line numbers |
| `parse_csv` | Row count, column stats, data quality issues: missing values, mixed `$`/bare numeric formats, inconsistent casing |
| `query_json` | Dot-path extraction (e.g. `app.features.DASHBOARD_V2`) |

`TOOL_REGISTRY` — `dict[str, Callable]` used by the loop dispatcher.

### `src/agent/loop.py`

Core of the assignment — async generator driving the agentic loop with streaming.

**Signature:**
```python
async def run_agent_stream(
    user_message: str,
    history: list[dict],       # OpenAI message format from prior turns
    store: DocumentStore,
    model: str | None = None,
    max_iterations: int | None = None,
) -> AsyncGenerator[StreamEvent, None]:
```

**Loop logic:**
```
For each iteration (up to max_iterations):
  1. Call OpenAI with stream=True, tools=TOOL_SCHEMAS, store=True, metadata={...}
  2. Accumulate streamed chunks:
       delta.content       → yield StreamEvent(type="content_delta")
       delta.tool_calls    → accumulate into buffer
  3. finish_reason == "stop"  → append final message, yield "done", return
  4. finish_reason == "tool_calls":
       a. Append assistant message with tool_calls payload
       b. For each tool: yield "tool_start" → execute → append result → yield "tool_end"
       c. Continue loop
Exhausted iterations → yield "error"
```

**Retry:** `_call_openai()` wraps `client.chat.completions.create` with tenacity — retries on `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError` (3 attempts, exponential backoff 1–10s).

**OpenAI platform traces:**
- `store=True` on every call (toggleable via `OPENAI_STORE_TRACES`)
- `project=OPENAI_PROJECT_ID` on the client — groups traces under your project
- `metadata={"app": "ai-document-assistant", "session_id": uuid, "iteration": n}`
- Completion ID logged at `DEBUG` level with direct URL

### `app/ui.py`

Gradio 6 `gr.Blocks` layout. Notes on Gradio 6 compatibility:
- `theme` moved from `gr.Blocks()` to `demo.launch(theme="soft")`
- `gr.Chatbot` — no `type` parameter; messages format is now default

**Layout:**
```
┌──────────────────────────────────────────────────────┐
│  AI-Document-Assistant                                │
├──────────────────┬───────────────────────────────────┤
│  Documents       │  gr.Chatbot                        │
│  [file list]     │                                    │
│                  │  [🔍 Reasoning Trace accordion]    │
│  [Upload]        │    gr.JSON — tool calls + outputs  │
│                  │                                    │
│  [Delete]        │  [Textbox input]  [Send]  [Clear]  │
└──────────────────┴───────────────────────────────────┘
```

**Streaming handler** (`chat_submit`):
- Yields on every `StreamEvent` — tokens appear in real time
- Tool-call status shown inline in the assistant bubble while agent works
- On `done`: finalises message, updates `oai_history` state, updates trace JSON

---

## Document Update Mechanism

No index or vector store — purely on-demand reads.

| Operation | How |
|---|---|
| Add document | Drop into `DOCUMENTS_DIR`, or use Gradio upload widget |
| Delete document | Delete manually, or use Gradio delete panel |
| Update document | Overwrite file; next query reads fresh content |
| Agent awareness | Agent calls `list_documents` first (instructed by system prompt) |

---

## Logging

- **Console + rotating file** (`LOG_DIR/app.log`)
- Rotation: `maxBytes = LOG_MAX_SIZE_MB × 1024²`, `backupCount = LOG_MAX_FILES - 1`
- Level hierarchy: `TRACE(5) < DEBUG(10) < INFO(20) < WARNING(30) < ERROR(40)`
- Key log events: agent start/done, each tool call + result snippet, LLM completion ID, retry attempts, file operations

---

## Tests (37 total, all passing)

| File | Tests | Covers |
|---|---|---|
| `test_document_store.py` | 10 | list/read/save/delete, path traversal, truncation, reflection of changes |
| `test_tools.py` | 20 | all 5 tools, CSV data quality (all 4 issues), JSON traversal, error paths |
| `test_loop.py` | 7 | single-turn, tool chaining, trace truncation, unknown tool, max iterations, history passing |

OpenAI calls mocked via `unittest.mock` — no real API calls in tests.
