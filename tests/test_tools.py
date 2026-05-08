from pathlib import Path

import pytest

from src.agent.tools import (
    list_documents,
    parse_csv,
    query_json,
    read_document,
    search_in_document,
)
from src.document_store import DocumentStore

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def store(tmp_docs_dir: Path) -> DocumentStore:
    return DocumentStore(str(tmp_docs_dir))


# ── list_documents ─────────────────────────────────────────────────────────────

async def test_list_documents_returns_all_files(store: DocumentStore):
    result = await list_documents(store)
    for name in ("meetings.md", "sales-q1.csv", "emails.txt", "config.json", "server-log.txt"):
        assert name in result


async def test_list_documents_markdown_table(store: DocumentStore):
    result = await list_documents(store)
    assert "| File |" in result
    assert "| Last Modified |" in result


async def test_list_documents_empty_dir(tmp_path: Path):
    empty_store = DocumentStore(str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    result = await list_documents(empty_store)
    assert "No documents" in result


# ── read_document ──────────────────────────────────────────────────────────────

async def test_read_document_returns_content(store: DocumentStore):
    result = await read_document(store, "config.json")
    assert '"Globe Platform"' in result


async def test_read_document_missing_file_returns_error(store: DocumentStore):
    result = await read_document(store, "ghost.txt")
    assert "Error" in result


# ── search_in_document ─────────────────────────────────────────────────────────

async def test_search_returns_matching_lines_with_numbers(store: DocumentStore):
    result = await search_in_document(store, "emails.txt", "Q1")
    assert "Line" in result
    assert "Q1" in result


async def test_search_is_case_insensitive(store: DocumentStore):
    lower = await search_in_document(store, "emails.txt", "q1")
    upper = await search_in_document(store, "emails.txt", "Q1")
    # Both should find the same number of matches; only the echoed query string differs
    lower_lines = [l for l in lower.splitlines() if l.startswith("Line")]
    upper_lines = [l for l in upper.splitlines() if l.startswith("Line")]
    assert lower_lines == upper_lines


async def test_search_no_match_returns_message(store: DocumentStore):
    result = await search_in_document(store, "emails.txt", "xyzzy_no_match_999")
    assert "No matches found" in result


async def test_search_missing_file_returns_error(store: DocumentStore):
    result = await search_in_document(store, "ghost.txt", "hello")
    assert "Error" in result


# ── parse_csv ──────────────────────────────────────────────────────────────────

async def test_parse_csv_detects_dollar_sign_format(store: DocumentStore):
    result = await parse_csv(store, "sales-q1.csv")
    assert "$49.00" in result or "mixed numeric" in result.lower() or "dollar" in result.lower() or "'$" in result


async def test_parse_csv_detects_missing_units_sold(store: DocumentStore):
    result = await parse_csv(store, "sales-q1.csv")
    assert "units_sold" in result
    assert "missing" in result.lower()


async def test_parse_csv_detects_missing_sales_rep(store: DocumentStore):
    result = await parse_csv(store, "sales-q1.csv")
    assert "sales_rep" in result
    assert "missing" in result.lower()


async def test_parse_csv_detects_inconsistent_casing(store: DocumentStore):
    result = await parse_csv(store, "sales-q1.csv")
    assert "casing" in result.lower() or "europe" in result.lower()


async def test_parse_csv_reports_row_count(store: DocumentStore):
    result = await parse_csv(store, "sales-q1.csv")
    assert "35" in result  # 35 data rows in sales-q1.csv


async def test_parse_csv_missing_file_returns_error(store: DocumentStore):
    result = await parse_csv(store, "no-such.csv")
    assert "Error" in result


# ── query_json ─────────────────────────────────────────────────────────────────

async def test_query_json_nested_bool(store: DocumentStore):
    result = await query_json(store, "config.json", "app.features.DASHBOARD_V2")
    assert "False" in result or "false" in result


async def test_query_json_nested_int(store: DocumentStore):
    result = await query_json(store, "config.json", "server.port")
    assert "8080" in result


async def test_query_json_string_value(store: DocumentStore):
    result = await query_json(store, "config.json", "app.environment")
    assert "production" in result


async def test_query_json_missing_key_returns_error(store: DocumentStore):
    result = await query_json(store, "config.json", "app.nonexistent.key")
    assert "not found" in result.lower() or "Error" in result


async def test_query_json_missing_file_returns_error(store: DocumentStore):
    result = await query_json(store, "ghost.json", "some.key")
    assert "Error" in result
