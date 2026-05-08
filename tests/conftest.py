import shutil
from pathlib import Path

import pytest

SAMPLE_DOCS = Path(__file__).parent.parent / "documents"


@pytest.fixture()
def tmp_docs_dir(tmp_path: Path) -> Path:
    """Copy sample documents into a temp directory for isolated tests."""
    docs = tmp_path / "documents"
    shutil.copytree(SAMPLE_DOCS, docs)
    return docs
