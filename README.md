# AI-Document-Assistant

Ask natural language questions about a collection of documents. An AI agent reads and analyzes them, showing its reasoning step by step.


#UI 
![1778242258907](image/README/1778242258907.png)


Logs
![1778242298060](image/README/1778242298060.png)


LLM Traces
![1778242321719](image/README/1778242321719.png)

---

## Features

- **Hand-rolled agent loop** — no LangChain, CrewAI, or similar frameworks. The agent decides which tools to call, executes them, and iterates until it has a complete answer.
- **5 tools**: list documents, read document, search within a document, parse CSV (with data quality detection), query JSON by dot-path.
- **Streaming UI** — tokens appear in real time; tool-call status is shown inline while the agent works.
- **Reasoning trace** — every tool call (name, input, full output) is shown in a scrollable collapsible panel after each answer.
- **Source attribution** — the agent ends every answer with a `**Sources:**` line listing the files it actually read or searched.
- **Document management** — upload and delete documents via the UI; the agent sees changes immediately (no re-indexing).
- **Async throughout** — `AsyncOpenAI` client, `aiofiles` for file I/O, async Gradio handlers.
- **Retry** — automatic retries on OpenAI rate limits, timeouts, and connection errors (tenacity, exponential backoff).
- **Logging** — rotating log files with configurable level (TRACE / DEBUG / INFO / WARNING / ERROR).
- **OpenAI platform traces** — every API call is stored and visible at platform.openai.com, grouped by project and session.

---

## Documents

The `documents/` folder contains the files the agent works with:

| File | Format | Description |
|---|---|---|
| `meetings.md` | Markdown | Meeting notes from a project team (3 meetings) |
| `sales-q1.csv` | CSV | Q1 sales data — contains intentional inconsistencies |
| `emails.txt` | Plain text | Email thread between team members about revenue discrepancies |
| `config.json` | JSON | Production application configuration |
| `server-log.txt` | Plain text | Server log with timestamps, errors, and warnings |

---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- OpenAI API key

---

## Install & Run

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd ai-document-assistant

# 2. Install dependencies
uv sync --extra dev

# 3. Configure environment
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY (and optionally OPENAI_PROJECT_ID)

# 4. Run
uv run python main.py
```

The app launches at **http://localhost:7860**.

---

## Configuration

All settings are in `.env`:

```env
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_PROJECT_ID=proj_...      # optional — groups traces on platform.openai.com

# Documents
DOCUMENTS_DIR=./documents       # path to your document folder
MAX_AGENT_ITERATIONS=10         # guard against infinite tool-call loops
MAX_FILE_SIZE_KB=100            # files larger than this are truncated

# OpenAI platform traces
OPENAI_STORE_TRACES=true        # set false to disable

# Logging
LOG_LEVEL=INFO                  # TRACE | DEBUG | INFO | WARNING | ERROR
LOG_DIR=./logs
LOG_MAX_FILES=10                # rotating: max 10 files on disk
LOG_MAX_SIZE_MB=10              # each file up to 10 MB
```

### Adding / removing documents

Drop files into `DOCUMENTS_DIR` (or use the Upload panel in the UI). The agent always calls `list_documents` first, so it sees the current state of the folder on every query. No re-indexing needed.

---

## Running Tests

```bash
uv run pytest tests/ -v
```

37 tests covering the document store, all 5 tools (including all 4 CSV data quality issues), and the agent loop. OpenAI calls are mocked — no real API calls during tests.

---

## Viewing LLM Traces on OpenAI Platform

1. Set `OPENAI_STORE_TRACES=true` and `OPENAI_PROJECT_ID=proj_xxx` in `.env`
   - Find your project ID at **platform.openai.com → Settings → Projects**
2. Run the app and ask a question
3. Go to **platform.openai.com → Traces**
4. Filter by `app = ai-document-assistant` in the metadata search
5. Each conversation shares a `session_id` — all its agent iterations are linked

The completion ID is also logged locally at `DEBUG` level with a direct URL.

---

## LLM API

**OpenAI** — `gpt-4o` via the `openai` Python SDK (async client, streaming, function calling).

---

## AI Coding Tools Used

This project was built with **Claude Code** (Anthropic's CLI coding assistant). Claude Code was used for:
- Architecture planning and design decisions
- Writing all source files and tests
- Debugging test failures and Gradio 6 API incompatibilities
- Researching the OpenAI tracing API via Context7 MCP

---

## Design Decisions

**Why no RAG?**
The document set is small (5 files, all fit in GPT-4o's 128K context). RAG would replace the agent's reasoning with cosine similarity — the agent actively deciding which files to read *is* the interesting part. If the document set grew to hundreds of files, a `search_documents` tool backed by embeddings would be added as one more tool the agent can call.

**Why hand-roll the agent loop?**
The assignment requires it, and it's the right call here. The loop is ~80 lines, easy to follow, and gives full control over streaming, retry, tracing, and error handling.

**Why Gradio 6?**
It's the current stable release. Key differences from 4.x: `theme` is passed to `launch()`, and the Chatbot uses messages format by default (no `type` parameter needed).

**Async throughout**
`AsyncOpenAI` + `aiofiles` + async Gradio handlers means no blocking I/O anywhere — the UI stays responsive during long agent runs.

**Retry strategy**
Tenacity handles OpenAI rate limits and transient errors at the API call level (exponential backoff), and transient OS errors at the file I/O level (fixed 0.5s wait). `FileNotFoundError` and `PermissionError` are not retried — they indicate logic errors, not transient failures.

**Logging**
A custom `TRACE` level (below `DEBUG`) lets you see raw LLM inputs/outputs without cluttering `DEBUG` logs during normal operation. Rotating file handler keeps at most `LOG_MAX_FILES` files on disk.

---

## Production Readiness — What Would Change

The current implementation is a working prototype. Here is what would need to change before running it in production:

### Security

- **Secrets management** — API keys must come from a secrets manager (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault), not `.env` files. `.env` is a local development convenience only.
- **Authentication & authorization** — the UI is currently open to anyone. Production needs user identity (OAuth / SSO), session tokens, and role-based access to control who can read, upload, or delete documents.
- **Document access control** — if different users should see different document sets, documents need per-user or per-tenant isolation (separate storage prefixes or buckets).
- **Input sanitization** — uploaded file names and content should be sanitized and scanned (e.g. ClamAV) before being written to disk.
- **HTTPS** — TLS termination via a reverse proxy (nginx, Caddy, or a cloud load balancer). Gradio's built-in server is not production-grade.

### Scalability & Architecture

- **Replace Gradio with a proper API + frontend** — Gradio is excellent for prototyping but not designed for multi-user production traffic. The right split: a FastAPI backend exposing `/chat` and `/documents` endpoints, and a React/Vue frontend consuming them via SSE for streaming.
- **Async task queue for long agent runs** — currently the agent runs synchronously in the request handler. Under load, long-running queries block Gradio workers. Move agent execution to a task queue (ARQ, Celery with `asyncio`, or a managed service) and stream results back via SSE or WebSocket.
- **Conversation persistence** — conversation history is currently in-memory and lost on restart. Use a database (PostgreSQL, Redis) to persist sessions, keyed by user + session ID.
- **Horizontal scaling** — stateless backend + persistent session store allows running multiple workers behind a load balancer.
- **Document storage** — local filesystem doesn't work across multiple instances. Move to object storage (S3, GCS, Azure Blob) with a thin abstraction layer (the `DocumentStore` interface already supports this — only `save_file`/`read_file`/`delete_file` need re-implementing).

### Reliability

- **Structured logging** — switch from plain-text log format to JSON (e.g. `python-json-logger`) so logs are ingestible by Datadog, Elasticsearch, or CloudWatch without parsing.
- **Distributed tracing** — add OpenTelemetry instrumentation. The OpenAI `session_id` metadata is a start; full traces should propagate through the HTTP request → agent loop → tool calls.
- **Error monitoring** — integrate Sentry (or equivalent) to capture and alert on unhandled exceptions in production.
- **Health check endpoint** — expose `GET /health` so load balancers and orchestrators (Kubernetes) can probe liveness and readiness.
- **Cost controls** — set hard token limits per request and per user per day. Monitor OpenAI spend via the Usage API and alert on anomalies.

### Large Document Sets

- **RAG / vector search** — once the document collection grows beyond ~50 files or includes very large files, add an embedding-backed `search_documents` tool. The agent loop doesn't change — it just gains one more tool to call.
- **Chunking strategy** — for large files (books, large logs), implement smarter chunking rather than hard truncation at `MAX_FILE_SIZE_KB`.
- **Document preprocessing pipeline** — add async background jobs to process newly uploaded documents (extract text from PDFs, normalize encodings, build search indexes).

### Testing & CI

- **End-to-end tests** — add Playwright tests against the running Gradio/API server for critical user flows.
- **Integration tests with real OpenAI calls** — run a small set of integration tests in CI against the actual API (with a test project and spend cap) to catch prompt regressions.
- **Load testing** — use Locust or k6 to validate the async task queue holds up under concurrent agent sessions.
- **Dependency pinning** — lock all dependency versions in `uv.lock` and run `uv sync --frozen` in CI to guarantee reproducible builds.
