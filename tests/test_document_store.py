import pytest
from pathlib import Path

from src.document_store import DocumentStore

pytestmark = pytest.mark.asyncio


async def test_list_files_returns_all_sample_docs(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    files = await store.list_files()
    names = {f.name for f in files}
    assert names == {"meetings.md", "sales-q1.csv", "emails.txt", "config.json", "server-log.txt"}


async def test_list_files_has_correct_metadata(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    files = await store.list_files()
    by_name = {f.name: f for f in files}

    csv_file = by_name["sales-q1.csv"]
    assert csv_file.extension == "csv"
    assert csv_file.size_bytes > 0
    assert csv_file.modified is not None


async def test_read_file_returns_content(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    content = await store.read_file("config.json")
    assert '"Globe Platform"' in content


async def test_read_file_nonexistent_raises(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    with pytest.raises(FileNotFoundError):
        await store.read_file("ghost.txt")


async def test_read_file_path_traversal_raises(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    with pytest.raises(PermissionError):
        await store.read_file("../../../etc/passwd")


async def test_read_file_truncates_large_file(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir), max_file_size_kb=1)
    big_file = tmp_docs_dir / "big.txt"
    big_file.write_text("x" * 2000)

    content = await store.read_file("big.txt")
    assert "[TRUNCATED" in content
    assert len(content) < 2000 + 200  # content + truncation notice


async def test_save_and_delete_roundtrip(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))

    await store.save_file("new_doc.txt", b"Hello world")
    assert await store.file_exists("new_doc.txt")

    content = await store.read_file("new_doc.txt")
    assert content == "Hello world"

    await store.delete_file("new_doc.txt")
    assert not await store.file_exists("new_doc.txt")


async def test_delete_nonexistent_raises(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    with pytest.raises(FileNotFoundError):
        await store.delete_file("ghost.txt")


async def test_list_files_reflects_new_upload(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    await store.save_file("uploaded.md", b"# New doc")
    files = await store.list_files()
    assert any(f.name == "uploaded.md" for f in files)


async def test_list_files_reflects_deletion(tmp_docs_dir: Path):
    store = DocumentStore(str(tmp_docs_dir))
    await store.delete_file("emails.txt")
    files = await store.list_files()
    assert not any(f.name == "emails.txt" for f in files)
