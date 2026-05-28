"""Unit tests for OpenPdf skill."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from oref import ProcessContext, SystemException, Transaction

from skills.open_pdf import OpenPdf


class TestOpenPdf:
    """Tests for OpenPdf skill."""

    def test_open_pdf_success(self, tmp_env: Path, sample_invoice_text: str, invoice_pdf: Path):
        """Test successful PDF opening with text content."""
        # Create a PDF with extractable text
        pdf_path = tmp_env / "test.pdf"
        # Use pdfplumber to create a proper PDF with text
        import pdfplumber
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.drawString(100, 700, sample_invoice_text)
        c.save()

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": str(pdf_path)},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_text" in ctx.data
        assert len(ctx.data["pdf_text"]) > 0
        assert "INV-2024-001" in ctx.data["pdf_text"]

    def test_open_pdf_missing_file_path(self, tmp_env: Path):
        """Test that missing file_path raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)

        with pytest.raises(SystemException, match="No file_path"):
            skill.execute(ctx)

    def test_open_pdf_file_not_found(self, tmp_env: Path):
        """Test that non-existent file raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": "/nonexistent/file.pdf"},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)

        with pytest.raises(SystemException, match="not found"):
            skill.execute(ctx)

    def test_open_pdf_empty_pdf(self, tmp_env: Path, empty_pdf: Path):
        """Test opening an empty PDF (no text content)."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": str(empty_pdf)},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_text" in ctx.data
        assert ctx.data["pdf_text"] == ""

    def test_open_pdf_sets_pdf_pages(self, tmp_env: Path, sample_invoice_text: str):
        """Test that open_pdf sets pdf_pages count."""
        pdf_path = tmp_env / "test.pdf"
        import pdfplumber
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.drawString(100, 700, sample_invoice_text)
        c.save()

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": str(pdf_path)},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_pages" in ctx.data
        assert ctx.data["pdf_pages"] >= 1

    def test_open_pdf_max_pages_limit(self, tmp_env: Path):
        """Test that max_pages config limits page count."""
        pdf_path = tmp_env / "test.pdf"
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        for i in range(5):
            c.drawString(100, 700, f"Page {i}")
            c.showPage()
        c.save()

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": str(pdf_path)},
            config={"max_pages": 2},
        )
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["pdf_pages"] == 2
