from dotenv import load_dotenv

load_dotenv()

from src.logger import setup_logging

log = setup_logging()

from app.ui import build_ui

if __name__ == "__main__":
    log.info("Starting AI-Document-Assistant")
    demo = build_ui()
    demo.launch(theme="soft")
