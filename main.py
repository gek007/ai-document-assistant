from dotenv import load_dotenv

load_dotenv()

from src.logger import setup_logging

log = setup_logging()

from app.ui import build_ui

if __name__ == "__main__":
    log.info("Starting AI-Document-Assistant")
    demo = build_ui()
    demo.launch(
        theme="soft",
        css="""
            footer { display: none !important; }
            #left-col { overflow-y: auto; }
            .example-qs button {
                text-align: left !important;
                justify-content: flex-start !important;
                background: var(--input-background-fill) !important;
                border: 1px solid var(--border-color-primary) !important;
                border-radius: var(--radius-sm) !important;
                color: var(--body-text-color) !important;
                font-weight: normal !important;
                white-space: normal !important;
                height: auto !important;
                padding: 6px 12px !important;
            }
        """,
    )
