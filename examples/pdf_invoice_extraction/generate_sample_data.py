"""Generate sample PDF invoices for testing the PDF invoice extraction example.

Creates sample PDF files in the sample_data/ directory with realistic
invoice content that can be processed by the pipeline.

Usage:
    python generate_sample_data.py [--output-dir sample_data]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _generate_basic_pdf(path: Path, lines: list[str]) -> None:
    """Generate a minimal PDF file with the given text lines.

    Uses reportlab if available, falls back to a minimal PDF structure.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(path), pagesize=letter)
        width, height = letter
        y = height - 50

        for line in lines:
            c.drawString(100, y, line)
            y -= 20
            if y < 50:
                c.showPage()
                y = height - 50
                c.drawString(100, y, line)
                y -= 20

        c.save()
    except ImportError:
        # Fallback: create a minimal PDF with the text as a comment
        # This won't be extractable by pdfplumber but allows the pipeline
        # to test error handling paths
        pdf_content = b"%PDF-1.0\n%%EOF\n"
        path.write_bytes(pdf_content)
        print(f"  [fallback] Created minimal PDF (reportlab not available): {path.name}")


def generate_sample_invoices(output_dir: str) -> None:
    """Generate sample invoice PDFs in the output directory."""
    sample_dir = Path(output_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)

    invoices = [
        {
            "filename": "invoice_001.pdf",
            "lines": [
                "INVOICE",
                "Invoice Number: INV-2024-001",
                "Date: 2024-01-15",
                "Bill From: Acme Corp",
                "",
                "Item Qty Unit Price",
                "Widget A 10 15.00",
                "Widget B 5 20.00",
                "",
                "Total: $275.00",
            ],
        },
        {
            "filename": "invoice_002.pdf",
            "lines": [
                "TAX INVOICE",
                "Invoice #: INV-2024-002",
                "Date: 2024-02-20",
                "From: Global Supplies Ltd",
                "",
                "Description Qty Unit Price",
                "Office Chair 3 150.00",
                "Desk Lamp 5 25.00",
                "Notebook Pack 10 8.50",
                "",
                "Total: $660.00",
            ],
        },
        {
            "filename": "invoice_003.pdf",
            "lines": [
                "INVOICE",
                "Invoice Number: INV-2024-003",
                "Date: 2024-03-10",
                "Bill From: Tech Solutions Inc",
                "",
                "Item Qty Unit Price",
                "Software License 1 500.00",
                "Support Annual 1 120.00",
                "",
                "Total: $620.00",
            ],
        },
        {
            "filename": "invoice_004.pdf",
            "lines": [
                "COMMERCIAL INVOICE",
                "Invoice Number: INV-2024-004",
                "Date: 2024-04-05",
                "Vendor: Euro Parts GmbH",
                "",
                "Item Qty Unit Price",
                "Steel Bolt M10 100 0.50",
                "Washer 10mm 200 0.10",
                "",
                "Total: €70.00",
            ],
        },
        {
            "filename": "invoice_005.pdf",
            "lines": [
                "INVOICE",
                "Invoice Number: INV-2024-005",
                "Date: 2024-05-01",
                "Bill From: Service Provider Co",
                "",
                "Item Qty Unit Price",
                "Consulting Hours 20 150.00",
                "Travel Expenses 1 350.00",
                "",
                "Total: $3,350.00",
            ],
        },
    ]

    for inv in invoices:
        pdf_path = sample_dir / inv["filename"]
        print(f"Generating: {pdf_path.name}")
        _generate_basic_pdf(pdf_path, inv["lines"])

    print(f"\nGenerated {len(invoices)} sample invoices in {output_dir}/")
    print("Note: If reportlab is not installed, these are minimal PDFs.")
    print("Install reportlab for proper PDF generation:")
    print("  pip install reportlab")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sample PDF invoices for testing."
    )
    parser.add_argument(
        "--output-dir",
        default="sample_data",
        help="Directory to write sample PDFs (default: sample_data)",
    )
    args = parser.parse_args()

    generate_sample_invoices(args.output_dir)


if __name__ == "__main__":
    main()
