"""Shared test fixtures for PDF Invoice Extraction tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rpacore import SqliteQueue, Transaction


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
    """Create a minimal PDF file with invoice text embedded as a comment."""
    pdf_path = tmp_path / "invoice_001.pdf"
    # Write a minimal PDF with text content that pdfplumber can extract
    pdf_content = (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"endobj\n"
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n"
        b"164\n"
        b"%%EOF\n"
    )
    pdf_path.write_bytes(pdf_content)
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
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.showPage()
    c.save()
    return pdf_path


@pytest.fixture
def valid_queue(tmp_path: Path) -> SqliteQueue:
    """Create a SqliteQueue in a temporary directory."""
    db_path = str(tmp_path / "test_queue.db")
    return SqliteQueue({"db_path": db_path, "max_retries": 2, "claim_timeout": 30})


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
        "db_path": str(tmp_path / "queue.db"),
        "sample_data_dir": sample_data_dir,
        "results_dir": results_dir,
        "output_csv": os.path.join(results_dir, "output.csv"),
    }


@pytest.fixture
def mock_queue() -> MagicMock:
    """Create a mock SqliteQueue for testing scan_inbox."""
    queue = MagicMock()
    queue.add = MagicMock()
    return queue
