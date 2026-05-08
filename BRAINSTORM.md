 ## quetion ... why we don't use RAG ?

Good question. Short answer: the documents are too small and too few for RAG to add value here, and it would actually hurt the assignment goals.

Here's the reasoning:

RAG solves a context window problem we don't have
RAG exists because you can't fit thousands of pages into an LLM's context. Our entire document set (5 files, all small) fits comfortably inside GPT-4o's 128K token window. There's nothing to retrieve — the agent can just read everything if needed.

The assignment is explicitly about the agent loop
The requirement says: "the part where the agent decides what to do, calls tools, observes results, and decides the next step." That decision-making IS the interesting part. With RAG, you replace the agent's reasoning with cosine similarity — the retrieval system picks the chunks, not the agent. Our agent actively decides: "this question is about sales, let me call list_documents, then parse_csv".

RAG is lossy for structured data
The CSV and JSON files benefit from programmatic parsing (parse_csv catches the $49.00 format issue, query_json extracts nested values). RAG would chunk those files as raw text and embed them, throwing away the structure. You'd lose the ability to detect data quality issues systematically.

Updates would be more complex
With RAG you'd need an embedding pipeline: add file → chunk → embed → upsert into vector store. In our design, adding a file is just dropping it in the folder. The agent calls list_documents and it's immediately visible.

When you'd choose RAG instead:
- Hundreds or thousands of documents
- Documents too large to read fully (books, large codebases)
- Fuzzy semantic search matters more than precise structured extraction

For this assignment, the agent-driven tool approach is both simpler and more capable for the given document set.

===============================

## If user will add new documents into repo ?

Great point. If the document set grows large, RAG becomes the right call. Here's how to think about the threshold:

Our current approach works fine up to ~50-100 small-to-medium documents. The agent calls list_documents, sees all files, and decides which to read. GPT-4o handles the context. No problem.

RAG becomes necessary when:
- There are so many documents that the list itself becomes overwhelming for the agent to reason about
- Individual documents are too large to read fully (the agent hits the MAX_FILE_SIZE_KB truncation)
- You want semantic search — "find documents related to payment failures" across hundreds of files

A pragmatic hybrid approach (if we wanted to future-proof it):

Small collection (< ~50 docs, all fit in context)
  → Current approach: agent reads on demand ✓

Large collection (100s of docs, or large files)
  → Add a search_documents(query) tool backed by embeddings
  → Agent still drives the loop, but instead of reading blindly,
    it searches first, then reads the top results

The key insight: RAG doesn't replace the agent loop, it becomes one more tool the agent can call. The agent still decides when to search, what to do with the results, and whether to read more. You keep the reasoning visible.

For this assignment's scope (5 known documents, manually managed folder), the current approach is correct. If you were building a production system where users continuously add documents, you'd add an embedding-backed search_documents tool and keep everything else the same.

Want me to note this as a "future extension" in the README when we implement?

## explain me about models

Two models, each with a clear job:

---
TraceStep — records one tool call the agent made:

class TraceStep(BaseModel):
    tool: str      # e.g. "parse_csv"
    input: dict    # e.g. {"filename": "sales-q1.csv"}
    output: str    # the result the tool returned (shown in reasoning trace UI)

One TraceStep is created every time the agent calls a tool. By the end of a conversation turn you have a list of them — that's the reasoning trace shown in the UI so the user can see how the agent arrived at the answer.

---
StreamEvent — a single message emitted by the agent loop generator:

class StreamEvent(BaseModel):
    type: Literal["tool_start", "tool_end", "content_delta", "done", "error"]
    content: str = ""
    trace: list[TraceStep] = []

The agent loop is an AsyncGenerator that yields these events one at a time. The UI listens and reacts to each:

┌───────────────┬───────────────────────────────┬───────────────────────────────┬──────────────────────────────────────────────────────┐
│     type      │             When              │         content holds         │                       UI does                        │
├───────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────────────────────────┤
│ tool_start    │ Agent is about to call a tool │ "🔧 Calling parse_csv..."     │ Shows status in the chat bubble                      │
├───────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────────────────────────┤
│ tool_end      │ Tool returned a result        │ "✅ parse_csv complete"       │ Updates status                                       │
├───────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────────────────────────┤
│ content_delta │ A token arrived from OpenAI   │ "The sales" / " data" / "..." │ Appends token to chat bubble (streaming effect)      │
├───────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────────────────────────┤
│ done          │ Agent finished answering      │ ""                            │ Finalises the message, updates reasoning trace panel │
├───────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────────────────────────┤
│ error         │ Tool or API failure           │ Error message                 │ Shows error in the chat bubble                       │
└───────────────┴───────────────────────────────┴───────────────────────────────┴──────────────────────────────────────────────────────┘

The trace field is only populated on done and error events — that's when the full list of steps is complete and ready to render.

---
In short: TraceStep is a data record, StreamEvent is a communication protocol between the agent loop and the UI.



## Logs 

┌───────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Change   │                                                                               Files                                                                                │
├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ UI        │ app/ui.py → "AI-Document-Assistant"                                                                                                                                │
│ caption   │                                                                                                                                                                    │
├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Logging   │ src/logger.py — TRACE/DEBUG/INFO/WARNING/ERROR, rotating file handler (max 10 files), configured via .env                                                          │
├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ LLM trace │ src/agent/loop.py — logs every API call (model, message count, finish reason, tool calls, result snippets)                                                         │
├───────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Retry     │ src/agent/loop.py — retries OpenAI on RateLimitError, APITimeoutError, APIConnectionError, InternalServerError (3 attempts, exponential backoff);                  │
│           │ src/document_store.py — retries transient OSError on read/save/delete