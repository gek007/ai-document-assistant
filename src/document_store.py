import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiofiles
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from src.logger import get_logger

log = get_logger(__name__)


@dataclass
class FileInfo:
    name: str
    size_bytes: int
    extension: str
    modified: datetime


def _is_transient_os_error(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and not isinstance(exc, (FileNotFoundError, PermissionError))


class DocumentStore:
    def __init__(self, documents_dir: str, max_file_size_kb: int = 100):
        self.documents_dir = Path(documents_dir).resolve()
        self.max_file_size_bytes = max_file_size_kb * 1024

    def _safe_path(self, filename: str) -> Path:
        """Guard against directory traversal attacks."""
        target = (self.documents_dir / filename).resolve()
        if not str(target).startswith(str(self.documents_dir) + os.sep) and target != self.documents_dir:
            raise PermissionError(f"Access denied: {filename!r} is outside the documents directory")
        return target

    async def list_files(self) -> list[FileInfo]:
        def _scan() -> list[FileInfo]:
            files = []
            for entry in os.scandir(self.documents_dir):
                if entry.is_file():
                    stat = entry.stat()
                    files.append(FileInfo(
                        name=entry.name,
                        size_bytes=stat.st_size,
                        extension=Path(entry.name).suffix.lstrip(".").lower(),
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    ))
            return sorted(files, key=lambda f: f.name)

        files = await asyncio.to_thread(_scan)
        log.debug("list_files: found %d file(s) in %s", len(files), self.documents_dir)
        return files

    @retry(
        retry=retry_if_exception(_is_transient_os_error),
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        reraise=True,
    )
    async def read_file(self, filename: str) -> str:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {filename!r}")

        size = path.stat().st_size
        log.debug("read_file: reading %s (%d bytes)", filename, size)

        async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
            content = await f.read()

        if size > self.max_file_size_bytes:
            limit_kb = self.max_file_size_bytes // 1024
            log.warning(
                "read_file: %s is %dKB, truncating to %dKB",
                filename, size // 1024, limit_kb,
            )
            return (
                content[: self.max_file_size_bytes]
                + f"\n\n[TRUNCATED: file is {size // 1024}KB, showing first {limit_kb}KB]"
            )

        return content

    @retry(
        retry=retry_if_exception(_is_transient_os_error),
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        reraise=True,
    )
    async def save_file(self, filename: str, content: bytes) -> None:
        path = self._safe_path(filename)
        log.info("save_file: writing %s (%d bytes)", filename, len(content))
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)

    @retry(
        retry=retry_if_exception(_is_transient_os_error),
        stop=stop_after_attempt(3),
        wait=wait_fixed(0.5),
        reraise=True,
    )
    async def delete_file(self, filename: str) -> None:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {filename!r}")
        log.info("delete_file: removing %s", filename)
        await asyncio.to_thread(path.unlink)

    async def file_exists(self, filename: str) -> bool:
        try:
            return self._safe_path(filename).exists()
        except PermissionError:
            return False


_store: DocumentStore | None = None


def get_store() -> DocumentStore:
    """Return the singleton DocumentStore configured from environment variables."""
    global _store
    if _store is None:
        documents_dir = os.environ.get("DOCUMENTS_DIR", "./documents")
        max_kb = int(os.environ.get("MAX_FILE_SIZE_KB", "100"))
        _store = DocumentStore(documents_dir, max_kb)
        log.info("DocumentStore initialised: dir=%s, max_file_size=%dKB", documents_dir, max_kb)
    return _store
