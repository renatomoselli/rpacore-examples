"""Write normalized invoice records to CSV and move source files."""

from __future__ import annotations

import csv
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

_CSV_HEADER = [
    "invoice_number",
    "date",
    "vendor",
    "line_items_count",
    "subtotal",
    "total",
    "currency",
]


class WriteOutput(Skill):
    """Write normalized invoice record to CSV output and move the source PDF to done/.

    On success: appends record to CSV, moves PDF to done/ folder.
    On validation failure: normalize_record raises SystemException (checking the
    validation_failed flag), short-circuiting execution before this skill runs.

    Expected input keys in ctx.data:
        - normalized_record: dict — Normalized invoice record from normalize_record
        - file_path: str — Original PDF file path

    Sets on ctx.data:
        - output_written: bool — True if record was written to CSV
    """

    def execute(self, ctx: ProcessContext) -> None:
        normalized_record = ctx.data.get("normalized_record")
        if normalized_record is None:
            raise SystemException(
                "No normalized_record in context — normalize_record must run first",
                action=self.name,
            )

        file_path = ctx.data.get("file_path")
        if file_path is None:
            raise SystemException(
                "No file_path in context — scan_inbox must run first",
                action=self.name,
            )

        results_dir = str(ctx.config.get("results_dir", "results"))
        output_csv = str(ctx.config.get("output_csv", "results/output.csv"))
        sample_data_dir = str(ctx.config.get("sample_data_dir", "sample_data"))

        Path(results_dir).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "done")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "failed")).mkdir(parents=True, exist_ok=True)

        # Write CSV record
        self._write_csv_record(output_csv, normalized_record)

        # Move the source PDF (skip if file doesn't exist — e.g. in tests)
        original_name = ctx.data.get("original_name", Path(file_path).name)
        if os.path.exists(file_path):
            dest_path = self._find_unique_dest(sample_data_dir, "done", original_name)
            shutil.move(file_path, dest_path)
            logger.info("Moved PDF to done/: %s", original_name)
        else:
            logger.info("Source PDF not found, skipping move: %s", file_path)

        ctx.data["output_written"] = True
        logger.info(
            "Wrote invoice %s to %s",
            normalized_record.get("invoice_number", "unknown"),
            output_csv,
        )

    def _write_csv_record(self, output_csv: str, invoice: dict) -> None:
        """Append a single invoice record to the CSV file.

        Skips if the invoice_number already exists in the CSV (idempotency guard).
        """
        invoice_number = invoice.get("invoice_number", "")
        file_exists = os.path.exists(output_csv)

        # Idempotency check: skip if this invoice was already written
        if file_exists and invoice_number:
            try:
                with open(output_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("invoice_number") == invoice_number:
                            logger.info(
                                "Skipping duplicate invoice %s (already in CSV)",
                                invoice_number,
                            )
                            return
            except (csv.Error, OSError):
                pass  # If we can't read, proceed with append (best-effort)

        with open(output_csv, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "invoice_number": invoice_number,
                "date": invoice.get("date", ""),
                "vendor": invoice.get("vendor", ""),
                "line_items_count": invoice.get("line_items_count", len(invoice.get("line_items", []))),
                "subtotal": self._format_decimal(invoice.get("subtotal")),
                "total": self._format_decimal(invoice.get("total")),
                "currency": invoice.get("currency", "USD"),
            })

    @staticmethod
    def _format_decimal(value: float | int | None) -> str:
        """Format a decimal value for CSV output."""
        if value is None:
            return ""
        return f"{float(value):.2f}"

    @staticmethod
    def _find_unique_dest(sample_data_dir: str, destination: str, name: str) -> str:
        """Find a unique destination path, appending a timestamp suffix if needed."""
        dest_dir = os.path.join(sample_data_dir, destination)
        dest_path = os.path.join(dest_dir, name)

        if not os.path.exists(dest_path):
            return dest_path

        # File exists — append timestamp suffix to avoid overwriting
        stem, ext = os.path.splitext(name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}{ext}")

        # Double-check in case of race
        if not os.path.exists(dest_path):
            return dest_path

        # Last resort: keep incrementing
        counter = 1
        while True:
            dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}_{counter}{ext}")
            if not os.path.exists(dest_path):
                return dest_path
            counter += 1
