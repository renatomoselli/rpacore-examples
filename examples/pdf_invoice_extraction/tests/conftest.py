"""Shared test fixtures for PDF Invoice Extraction tests."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from rpacore import SqliteQueue, Transaction

@pytest.fixture(autouse=True)
def fake_pdfplumber(monkeypatch):
    """Provide deterministic PDF text extraction without native PDF dependencies."""

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdf:
        def __init__(self, path: str) -> None:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            page_texts = text.split("\f") if text else [""]
            self.pages = [FakePage(page_text) for page_text in page_texts]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def open_pdf(path: str) -> FakePdf:
        return FakePdf(path)

    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=open_pdf))

@pytest.fixture
def tmp_env(tmp_path: Path) -> str:
    """Create a temporary directory and set it as CWD for isolation."""
    original_cwd = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        yield tmp_path
    finally:
        os.chdir(original_cwd)

@pytest.fixture
def sample_pdf_content() -> bytes:
    """Return a minimal valid PDF file content."""
    return (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>>>endobj\n"
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"trailer<</Size 5/Root 1 0 R>>\n"
        b"startxref\n"
        b"324\n"
        b"%%EOF\n"
    )

@pytest.fixture
def invoice_pdf(tmp_path: Path, sample_pdf_content: bytes) -> Path:
    """Create a deterministic text-backed PDF fixture."""
    pdf_path = tmp_path / "invoice_001.pdf"
    pdf_path.write_text(
        "Invoice Number: INV-2024-001\n"
        "Date: 2024-01-15\n"
        "Bill From: Acme Corp\n"
        "Widget A 10 $15.00\n"
        "Widget B 5 $20.00\n"
        "Total: $250.00",
        encoding="utf-8",
    )
    return pdf_path

@pytest.fixture
def sample_invoice_text() -> str:
    """Return sample invoice text for testing the parser."""
    return (
        "INVOICE\n"
        "Invoice Number: INV-2024-001\n"
        "Date: 2024-01-15\n"
        "Bill From: Acme Corp\n"
        "\n"
        "Item\tQty\tUnit Price\n"
        "Widget A\t10\t$15.00\n"
        "Widget B\t5\t$20.00\n"
        "\n"
        "Subtotal: $250.00\n"
        "Total: $275.00\n"
    )

@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create a valid PDF with no text content (extracts empty string)."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_text("", encoding="utf-8")
    return pdf_path

@pytest.fixture
def valid_queue(tmp_path: Path) -> SqliteQueue:
    """Create a SqliteQueue in a temporary directory."""
    db_path = str(tmp_path / "test_queue.db")
    return SqliteQueue({"db_path": db_path, "max_retries": 2, "lease_timeout": 30})

@pytest.fixture
def sample_config(tmp_path: Path) -> dict:
    """Create a sample config dict for testing."""
    results_dir = str(tmp_path / "results")
    sample_data_dir = str(tmp_path / "sample_data")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(sample_data_dir, exist_ok=True)
    return {
        "max_retries": 2,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "sample_data_dir": sample_data_dir,
        "results_dir": results_dir,
        "output_csv": os.path.join(results_dir, "output.csv"),
        "max_pages": 100,
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }

@pytest.fixture
def mock_queue() -> MagicMock:
    """Create a mock SqliteQueue for testing scan_inbox."""
    queue = MagicMock()
    queue.add_once = MagicMock(return_value=True)
    return queue
