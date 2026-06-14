"""Generate sample PDF invoice data for testing."""

from __future__ import annotations

import os
from pathlib import Path

# Sample invoice data with correct arithmetic:
# Widget A: 10 × $15.00 = $150.00
# Widget B: 5 × $20.00 = $100.00
# Total: $250.00
_SAMPLE_INVOICES = [
    {
        "filename": "invoice_001.pdf",
        "text": (
            "Invoice Number: INV-2024-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Acme Corp\n"
            "Widget A  10  $15.00\n"
            "Widget B  5  $20.00\n"
            "Total: $250.00"
        ),
    },
    {
        "filename": "invoice_002.pdf",
        "text": (
            "Invoice Number: INV-2024-002\n"
            "Date: 2024-02-20\n"
            "Bill From: Global Supplies\n"
            "Service B  4  $50.00\n"
            "Total: $200.00"
        ),
    },
    {
        "filename": "invoice_003.pdf",
        "text": (
            "Invoice Number: INV-2024-003\n"
            "Date: 2024-03-10\n"
            "Bill From: Tech Solutions\n"
            "Service C  3  $100.00\n"
            "Total: $300.00"
        ),
    },
]

def generate_sample_data(output_dir: str = "sample_data") -> None:
    """Generate sample PDF invoice files."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for invoice in _SAMPLE_INVOICES:
        pdf_path = os.path.join(output_dir, invoice["filename"])
        _create_pdf_with_text(pdf_path, invoice["text"])
        print(f"Created: {pdf_path}")

    print(f"Generated {len(_SAMPLE_INVOICES)} sample invoices in {output_dir}/")

def _create_pdf_with_text(pdf_path: str, text: str) -> None:
    """Create a minimal PDF with extractable text."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "reportlab is required to generate sample PDFs. "
            "Install this example's requirements with: pip install -r requirements.txt"
        ) from exc

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    y = height - 50
    for line in text.split("\n"):
        line = line.replace("\t", "  ")
        c.drawString(100, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()

if __name__ == "__main__":
    generate_sample_data()
