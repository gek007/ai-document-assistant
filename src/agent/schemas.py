TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": (
                "List all documents available in the documents directory with name, size, type, "
                "and last modified date. Always call this first to know what files are available."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": (
                "Read the full content of a document by filename. "
                "Use for markdown, plain text, log files, and JSON files you want to read in full. "
                "For CSV files prefer parse_csv instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename to read (e.g. 'meetings.md')",
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_document",
            "description": (
                "Search for a query string within a document and return matching lines with line numbers. "
                "Useful for finding specific entries in logs, emails, or meeting notes without reading the whole file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to search in"},
                    "query": {"type": "string", "description": "Search string (case-insensitive)"},
                },
                "required": ["filename", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_csv",
            "description": (
                "Parse a CSV file and return a structured summary: row count, column names, "
                "per-column stats, and data quality issues (missing values, mixed numeric formats, "
                "inconsistent casing). Always use this for CSV files instead of read_document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The CSV filename to parse"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_json",
            "description": (
                "Extract a specific value from a JSON file using a dot-separated path "
                "(e.g. 'app.features.DASHBOARD_V2' or 'server.port'). "
                "Use for targeted lookups instead of reading the whole file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The JSON filename"},
                    "path": {
                        "type": "string",
                        "description": "Dot-separated key path (e.g. 'app.version')",
                    },
                },
                "required": ["filename", "path"],
            },
        },
    },
]
