import os
from pathlib import Path

import gradio as gr

from src.agent.loop import run_agent_stream
from src.document_store import DocumentStore, get_store


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _doc_list_md(store: DocumentStore) -> str:
    files = await store.list_files()
    if not files:
        return "_No documents found. Upload one to get started._"
    lines = ["| File | Size | Type |", "|---|---|---|"]
    for f in files:
        size = f"{f.size_bytes // 1024} KB" if f.size_bytes >= 1024 else f"{f.size_bytes} B"
        lines.append(f"| `{f.name}` | {size} | {f.extension or '?'} |")
    return "\n".join(lines)


async def _file_choices(store: DocumentStore) -> list[str]:
    files = await store.list_files()
    return [f.name for f in files]


# ── UI builder ─────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    store = get_store()

    # ── Layout ─────────────────────────────────────────────────────────────────
    with gr.Blocks(title="AI-Document-Assistant") as demo:
        gr.Markdown("# AI-Document-Assistant")
        gr.Markdown("Ask natural language questions about your documents.")

        oai_history = gr.State([])   # OpenAI-format conversation history
        trace_state = gr.State([])   # list of TraceStep dicts

        with gr.Row(equal_height=False):

            # ── Left panel: document management ────────────────────────────────
            with gr.Column(scale=1, min_width=260):
                gr.Markdown("### Documents")
                doc_list = gr.Markdown()
                refresh_btn = gr.Button("🔄 Refresh", size="sm")

                gr.Markdown("### Upload")
                upload = gr.File(
                    label="Add documents",
                    file_count="multiple",
                    file_types=[".md", ".txt", ".csv", ".json", ".log"],
                )

                gr.Markdown("### Delete")
                delete_dd = gr.Dropdown(label="Select file", choices=[], interactive=True)
                delete_btn = gr.Button("🗑️ Delete selected", size="sm", variant="stop")

            # ── Right panel: chat ───────────────────────────────────────────────
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    height=480,
                    label="Chat",
                    show_label=False,
                    render_markdown=True,
                )

                with gr.Accordion("🔍 Reasoning trace", open=False):
                    trace_display = gr.JSON(label="Tool calls made by the agent")

                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="Ask a question about your documents…",
                        show_label=False,
                        scale=5,
                        autofocus=True,
                        lines=1,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                clear_btn = gr.Button("🗑️ Clear conversation", size="sm")

                gr.Examples(
                    examples=[
                        ["What files do you have access to?"],
                        ["What was decided in the March 12 meeting?"],
                        ["Are there any data quality issues in the sales CSV?"],
                        ["Did anyone mention Q1 sales in the emails? How do they compare to the actual CSV data?"],
                        ["Are there any errors in the server log that might relate to the config settings?"],
                        ["What is the database host and port from config.json?"],
                    ],
                    inputs=[msg_input],
                    label="Example questions (click to copy)",
                )

        # ── Event handlers ──────────────────────────────────────────────────────

        async def refresh():
            md = await _doc_list_md(store)
            choices = await _file_choices(store)
            return md, gr.update(choices=choices, value=None)

        async def handle_upload(files):
            for file in files or []:
                path = Path(file.name)
                await store.save_file(path.name, path.read_bytes())
            return await refresh()

        async def handle_delete(filename):
            if filename:
                await store.delete_file(filename)
            return await refresh()

        async def chat_submit(user_msg, chatbot_hist, oai_hist, trace):
            if not user_msg.strip():
                yield chatbot_hist, oai_hist, trace, user_msg, trace
                return

            chatbot_hist = chatbot_hist + [{"role": "user", "content": user_msg}]
            yield chatbot_hist, oai_hist, trace, "", trace  # clear input immediately

            assistant_content = ""
            status_line = ""

            async for event in run_agent_stream(user_msg, oai_hist, store):
                if event.type == "content_delta":
                    assistant_content += event.content
                    status_line = ""
                    bubble = assistant_content

                elif event.type == "tool_start":
                    status_line = f"\n\n*{event.content}…*"
                    bubble = (assistant_content or "*Working…*") + status_line

                elif event.type == "tool_end":
                    status_line = ""
                    bubble = assistant_content or "*Working…*"

                elif event.type == "done":
                    bubble = assistant_content
                    oai_hist = oai_hist + [
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": assistant_content},
                    ]
                    trace = [s.model_dump() for s in event.trace]

                elif event.type == "error":
                    bubble = f"⚠️ {event.content}"
                    trace = [s.model_dump() for s in event.trace]

                else:
                    continue

                yield (
                    chatbot_hist + [{"role": "assistant", "content": bubble}],
                    oai_hist,
                    trace,
                    "",
                    trace,
                )

        def clear_conversation():
            return [], [], [], ""

        # ── Wire events ─────────────────────────────────────────────────────────

        doc_refresh_outputs = [doc_list, delete_dd]

        demo.load(refresh, outputs=doc_refresh_outputs)
        refresh_btn.click(refresh, outputs=doc_refresh_outputs)
        upload.change(handle_upload, inputs=[upload], outputs=doc_refresh_outputs)
        delete_btn.click(handle_delete, inputs=[delete_dd], outputs=doc_refresh_outputs)

        chat_outputs = [chatbot, oai_history, trace_state, msg_input, trace_display]
        send_btn.click(chat_submit, inputs=[msg_input, chatbot, oai_history, trace_state], outputs=chat_outputs)
        msg_input.submit(chat_submit, inputs=[msg_input, chatbot, oai_history, trace_state], outputs=chat_outputs)

        clear_btn.click(clear_conversation, outputs=[chatbot, oai_history, trace_state, msg_input])

    return demo
