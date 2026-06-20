"""Unit tests for sample PDF generation."""

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace

import pytest

import generate_sample_data as sample_data_module
from generate_sample_data import (
    _SAMPLE_INVOICES,
    _create_pdf_with_text,
    generate_sample_data,
)


def test_sample_invoice_text_uses_spaces_not_tabs():
    """ReportLab/pdfplumber handles spaces more reliably than tab glyphs."""
    assert all("\t" not in invoice["text"] for invoice in _SAMPLE_INVOICES)


def test_generate_sample_data_creates_every_sample(tmp_path, monkeypatch):
    created = []
    monkeypatch.setattr(
        sample_data_module,
        "_create_pdf_with_text",
        lambda path, text: created.append((path, text)),
    )

    generate_sample_data(str(tmp_path))

    assert [path for path, _ in created] == [
        str(tmp_path / invoice["filename"]) for invoice in _SAMPLE_INVOICES
    ]
    assert [text for _, text in created] == [
        invoice["text"] for invoice in _SAMPLE_INVOICES
    ]


def test_pdf_generator_replaces_tabs_before_drawing(tmp_path, monkeypatch):
    """The drawing layer should be guarded even if future sample text adds tabs."""
    drawn_lines = []

    class FakeCanvas:
        def __init__(self, path, pagesize):
            self.path = path
            self.pagesize = pagesize

        def drawString(self, x, y, line):
            drawn_lines.append(line)

        def showPage(self):
            pass

        def save(self):
            pass

    fake_reportlab = SimpleNamespace()
    fake_lib = SimpleNamespace()
    fake_pdfgen = SimpleNamespace()
    fake_pagesizes = SimpleNamespace(letter=(612, 792))
    fake_canvas_module = SimpleNamespace(Canvas=FakeCanvas)
    fake_lib.pagesizes = fake_pagesizes
    fake_pdfgen.canvas = fake_canvas_module
    fake_reportlab.lib = fake_lib
    fake_reportlab.pdfgen = fake_pdfgen

    monkeypatch.setitem(sys.modules, "reportlab", fake_reportlab)
    monkeypatch.setitem(sys.modules, "reportlab.lib", fake_lib)
    monkeypatch.setitem(sys.modules, "reportlab.lib.pagesizes", fake_pagesizes)
    monkeypatch.setitem(sys.modules, "reportlab.pdfgen", fake_pdfgen)
    monkeypatch.setitem(sys.modules, "reportlab.pdfgen.canvas", fake_canvas_module)

    _create_pdf_with_text(str(tmp_path / "invoice.pdf"), "Widget\t10\t$15.00")

    assert drawn_lines == ["Widget  10  $15.00"]


def test_pdf_generator_requires_reportlab(tmp_path, monkeypatch):
    """Missing reportlab should fail clearly instead of writing an invalid PDF."""
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError("reportlab missing")
        return original_import(name, *args, **kwargs)

    pdf_path = tmp_path / "invoice.pdf"
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="reportlab is required"):
        _create_pdf_with_text(str(pdf_path), "Invoice Number: INV-001")

    assert not pdf_path.exists()
