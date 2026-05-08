from dotenv import load_dotenv

load_dotenv()

from app.ui import build_ui

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(theme="soft")
