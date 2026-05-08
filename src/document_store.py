import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiofiles


@dataclass
class FileInfo:
    name: str
    size_bytes: int
    extension: str
    modified: datetime


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

        return await asyncio.to_thread(_scan)

    async def read_file(self, filename: str) -> str:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {filename!r}")

        size = path.stat().st_size
        async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
            content = await f.read()

        if size > self.max_file_size_bytes:
            truncated = content[: self.max_file_size_bytes]
            limit_kb = self.max_file_size_bytes // 1024
            return (
                truncated
                + f"\n\n[TRUNCATED: file is {size // 1024}KB, showing first {limit_kb}KB]"
            )

        return content

    async def save_file(self, filename: str, content: bytes) -> None:
        path = self._safe_path(filename)
        async with aiofiles.open(path, "wb") as f:
            await f.write(content)

    async def delete_file(self, filename: str) -> None:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {filename!r}")
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
    return _store
