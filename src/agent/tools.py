import csv
import io
import json
from typing import Any

from src.agent.helpers import is_numeric
from src.document_store import DocumentStore


# ── Tool implementations ───────────────────────────────────────────────────────

async def list_documents(store: DocumentStore) -> str:
    files = await store.list_files()
    if not files:
        return "No documents found in the documents directory."

    lines = ["| File | Size | Type | Last Modified |", "|---|---|---|---|"]
    for f in files:
        size = f"{f.size_bytes:,} bytes" if f.size_bytes < 1024 else f"{f.size_bytes // 1024} KB"
        lines.append(
            f"| {f.name} | {size} | {f.extension or 'unknown'} | {f.modified.strftime('%Y-%m-%d %H:%M')} |"
        )
    return "\n".join(lines)


async def read_document(store: DocumentStore, filename: str) -> str:
    try:
        return await store.read_file(filename)
    except (FileNotFoundError, PermissionError) as e:
        return f"Error: {e}"


async def search_in_document(store: DocumentStore, filename: str, query: str) -> str:
    try:
        content = await store.read_file(filename)
    except (FileNotFoundError, PermissionError) as e:
        return f"Error: {e}"

    query_words = [word.lower() for word in query.strip().split()]
    matches = [
        f"Line {i + 1}: {line}"
        for i, line in enumerate(content.splitlines())
        if all(word in line.lower() for word in query_words)
    ]

    if not matches:
        return f"No matches found for {query!r} in {filename!r}."

    return f"Found {len(matches)} match(es) for {query!r} in {filename!r}:\n\n" + "\n".join(matches)


async def parse_csv(store: DocumentStore, filename: str) -> str:
    try:
        content = await store.read_file(filename)
    except (FileNotFoundError, PermissionError) as e:
        return f"Error: {e}"

    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        return f"{filename!r} is empty or has no data rows."

    columns = list(reader.fieldnames or [])
    issues: list[str] = []
    col_values: dict[str, list[str]] = {col: [] for col in columns}

    for row_idx, row in enumerate(rows, start=2):  # row 1 is header
        for col in columns:
            val = (row.get(col) or "").strip()
            col_values[col].append(val)
            if val == "":
                issues.append(f"Row {row_idx}: missing value in column '{col}'")

    # Mixed numeric formats (e.g. "$49.00" vs "49.00")
    for col in columns:
        vals = [v for v in col_values[col] if v]
        dollar_vals = [v for v in vals if v.startswith("$")]
        bare_vals = [v for v in vals if not v.startswith("$") and is_numeric(v)]
        if dollar_vals and bare_vals:
            issues.append(
                f"Column '{col}': mixed numeric formats — "
                f"{len(dollar_vals)} value(s) with '$' prefix (e.g. {dollar_vals[0]!r}) "
                f"vs bare numbers (e.g. {bare_vals[0]!r})"
            )

    # Inconsistent casing in string columns
    for col in columns:
        vals = [v for v in col_values[col] if v]
        lower_map: dict[str, list[str]] = {}
        for v in set(vals):
            lower_map.setdefault(v.lower(), []).append(v)
        for variants in lower_map.values():
            if len(variants) > 1:
                issues.append(f"Column '{col}': inconsistent casing — found {sorted(variants)}")

    # Per-column summary
    col_summaries = []
    for col in columns:
        vals = [v for v in col_values[col] if v]
        missing = len(col_values[col]) - len(vals)
        summary = f"  - {col}: {len(set(vals))} unique value(s)"
        if missing:
            summary += f", {missing} missing"
        col_summaries.append(summary)

    result = [
        f"**{filename}** — CSV summary",
        f"- Rows: {len(rows)} (excluding header)",
        f"- Columns ({len(columns)}): {', '.join(columns)}",
        "",
        "**Per-column stats:**",
        *col_summaries,
    ]

    if issues:
        result += ["", f"**Data quality issues ({len(issues)} found):**"]
        result += [f"  ⚠️  {issue}" for issue in issues]
    else:
        result.append("\n✅ No data quality issues detected.")

    return "\n".join(result)


async def query_json(store: DocumentStore, filename: str, path: str) -> str:
    try:
        content = await store.read_file(filename)
    except (FileNotFoundError, PermissionError) as e:
        return f"Error: {e}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return f"Error: {filename!r} is not valid JSON — {e}"

    current: Any = data
    traversed: list[str] = []

    for key in path.split("."):
        traversed.append(key)
        if isinstance(current, dict):
            if key not in current:
                return f"Key not found: {'.'.join(traversed)!r} does not exist in {filename!r}"
            current = current[key]
        else:
            return (
                f"Cannot traverse into {type(current).__name__} "
                f"at {'.'.join(traversed[:-1])!r}"
            )

    value_repr = json.dumps(current, indent=2) if isinstance(current, (dict, list)) else str(current)
    return f"**{path}** = `{value_repr}` (type: {type(current).__name__})"


# ── Tool registry ──────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Any] = {
    "list_documents": list_documents,
    "read_document": read_document,
    "search_in_document": search_in_document,
    "parse_csv": parse_csv,
    "query_json": query_json,
}
