import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ── Custom TRACE level (below DEBUG=10) ───────────────────────────────────────

TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(self: logging.Logger, message: Any, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_dir = Path(os.environ.get("LOG_DIR", "./logs"))
    max_files = int(os.environ.get("LOG_MAX_FILES", "10"))
    max_size_mb = int(os.environ.get("LOG_MAX_SIZE_MB", "10"))
    log_output = os.environ.get("LOG_OUTPUT", "both").lower()  # values: terminal | file | both

    level = TRACE if level_name == "TRACE" else getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers: list[logging.Handler] = []

    if log_output in ("terminal", "both"):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        handlers.append(console)

    if log_output in ("file", "both"):
        log_dir.mkdir(parents=True, exist_ok=True)
        # RotatingFileHandler: backupCount = max_files - 1 so total on-disk = max_files
        file_handler = RotatingFileHandler(
            filename=log_dir / "app.log",
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=max_files - 1,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if called more than once (e.g. in tests)
    if not root.handlers:
        for h in handlers:
            root.addHandler(h)

    return logging.getLogger("app")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
