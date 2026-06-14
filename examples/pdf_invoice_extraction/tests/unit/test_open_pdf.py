"""Unit tests for OpenPdf skill."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from skills.open_pdf import OpenPdf

class TestOpenPdf:
    """Tests for OpenPdf skill."""

    def test_open_pdf_success(self, tmp_env: Path, sample_invoice_text: str, invoice_pdf: Path):
        """Test successful PDF opening with text content."""
        pdf_path = tmp_env / "test.pdf"
        pdf_path.write_text(sample_invoice_text, encoding="utf-8")

        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = str(pdf_path)
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_text" in tx.state
        assert len(tx.state["pdf_text"]) > 0
        assert "INV-2024-001" in tx.state["pdf_text"]

    def test_open_pdf_missing_file_path(self, tmp_env: Path):
        """Test that missing file_path raises SystemException."""
        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)

        with pytest.raises(SystemException, match="file_path"):
            skill.execute(ctx)

    def test_open_pdf_file_not_found(self, tmp_env: Path):
        """Test that non-existent file raises SystemException."""
        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = "/nonexistent/file.pdf"
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)

        with pytest.raises(SystemException, match="not found"):
            skill.execute(ctx)

    def test_open_pdf_directory_path(self, tmp_env: Path):
        """Test that a directory path raises SystemException."""
        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = str(tmp_env)
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)

        with pytest.raises(SystemException, match="not a file"):
            skill.execute(ctx)

    def test_open_pdf_empty_pdf(self, tmp_env: Path, empty_pdf: Path):
        """Test opening an empty PDF (no text content)."""
        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = str(empty_pdf)
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_text" in tx.state
        assert tx.state["pdf_text"] == ""

    def test_open_pdf_sets_pdf_pages(self, tmp_env: Path, sample_invoice_text: str):
        """Test that open_pdf sets pdf_pages count."""
        pdf_path = tmp_env / "test.pdf"
        pdf_path.write_text(sample_invoice_text, encoding="utf-8")

        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = str(pdf_path)
        ctx = ProcessContext(transaction=tx, config={})
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert "pdf_pages" in tx.state
        assert tx.state["pdf_pages"] >= 1

    def test_open_pdf_max_pages_limit(self, tmp_env: Path):
        """Test that max_pages config limits page count."""
        pdf_path = tmp_env / "test.pdf"
        pdf_path.write_text("\f".join(f"Page {i}" for i in range(5)), encoding="utf-8")

        tx = Transaction(reference="test", skills=[OpenPdf(name="open_pdf", execution_order=1)])
        tx.state["file_path"] = str(pdf_path)
        ctx = ProcessContext(transaction=tx, config={"max_pages": 2})
        skill = OpenPdf(name="open_pdf", execution_order=1)
        skill.execute(ctx)

        assert tx.state["pdf_pages"] == 2
