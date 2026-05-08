# Implementation Order

Each step unblocks the next. Stop for code review and commit after each step from #3 onwards.

1. **`pyproject.toml`** — add all dependencies (`openai`, `gradio`, `python-dotenv`, `pydantic`, `aiofiles`, `tenacity`), run `uv sync --extra dev`
   > Everything else imports from these packages.

2. **`.env.example` + `.env`** — all config keys including logging and OpenAI trace settings
   > Code reads env vars from the start; needs to exist before running anything.

3. **`src/logger.py`** — logging setup: custom TRACE level, rotating file handler, `get_logger()`
   > Used by document_store and loop; set up before any other module logs.

4. **`src/document_store.py`** — async file I/O, path traversal guard, tenacity retry, `get_store()` singleton
   > All tools depend on this. No business logic here.

5. **`src/models.py`** — `TraceStep`, `StreamEvent` Pydantic models
   > Shared types used by agent loop and UI.

6. **`src/agent/helpers.py`** — `is_numeric()` utility
   > Used by `parse_csv` tool.

7. **`src/agent/schemas.py`** — `TOOL_SCHEMAS` (5 OpenAI function definitions)
   > Consumed by the agent loop; kept separate from implementations.

8. **`src/agent/tools.py`** — 5 async tool implementations + `TOOL_REGISTRY`
   > Depends on document_store, helpers.

9. **`src/agent/loop.py`** — async streaming agent loop, OpenAI retry, LLM trace logging, platform traces
   > Core of the assignment. Depends on tools, schemas, models, logger.

10. **`tests/`** — `conftest.py`, `test_document_store.py`, `test_tools.py`, `test_loop.py`
    > Write and verify after each module is complete.

11. **`app/ui.py`** — Gradio 6 layout, streaming chat handler, document management panel
    > Depends on the loop being correct. UI is wired up last.

12. **`main.py`** — entry point: load `.env` → init logging → launch Gradio
    > One-liner orchestration.

13. **`README.md`** — install/run instructions, design decisions, AI tools used
    > Last, once everything is verified working.

---

## Gradio 6 Notes

- `theme` is passed to `demo.launch(theme="soft")`, not `gr.Blocks()`
- `gr.Chatbot` has no `type` parameter — messages format (`[{"role": ..., "content": ...}]`) is the default
- Async generator functions are supported natively as streaming event handlers

## OpenAI Traces Setup

1. Go to **platform.openai.com → Settings → Projects**
2. Create or select a project (e.g. "AI-Document-Assistant")
3. Copy the project ID (`proj_xxx`) into `.env` as `OPENAI_PROJECT_ID`
4. Set `OPENAI_STORE_TRACES=true`
5. Run the app — traces appear at **platform.openai.com → Traces**, filterable by `app = ai-document-assistant`
