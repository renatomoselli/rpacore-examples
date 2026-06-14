"""Write normalized invoice records to CSV and move source files."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

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

    On success: moves PDF to done/, atomically appends record to CSV, and registers artifacts.
    On duplicate: raises BusinessException (stop=True) for duplicate invoice numbers.
    """

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            logger.info("Validation failed earlier; skipping output write.")
            return

        normalized_record = ctx.require_state("normalized_record", dict, action=self.name)
        file_path = ctx.require_state("file_path", str, action=self.name)

        results_dir = str(ctx.config.get("results_dir", "results"))
        output_csv = str(ctx.config.get("output_csv", "results/output.csv"))
        sample_data_dir = str(ctx.config.get("sample_data_dir", "sample_data"))

        Path(results_dir).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "done")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "failed")).mkdir(parents=True, exist_ok=True)

        # Validate duplicate/corrupt CSV state before moving the source PDF.
        self._ensure_invoice_not_written(output_csv, normalized_record)

        original_name = ctx.optional_state(
            "original_name", str, Path(file_path).name, action=self.name
        )
        dest_path = ctx.optional_state("done_path", str, "", action=self.name) or None
        if os.path.exists(file_path):
            if dest_path is None:
                dest_path = self._find_unique_dest(sample_data_dir, "done", original_name)
                ctx.state["done_path"] = dest_path
            try:
                shutil.move(file_path, dest_path)
            except OSError as exc:
                raise SystemException(
                    f"Failed to move PDF to done/: {exc}",
                    action=self.name,
                ) from exc
            logger.info("Moved PDF to done/: %s", original_name)
        else:
            logger.info("Source PDF not found, skipping move: %s", file_path)

        self._write_csv_record(output_csv, normalized_record)
        ctx.state["output_written"] = True

        ctx.add_artifact(
            "invoice_csv",
            output_csv,
            kind="csv",
            metadata={
                "invoice_number": normalized_record.get("invoice_number", ""),
                "vendor": normalized_record.get("vendor", ""),
                "source_file": original_name,
            },
        )
        if dest_path is not None:
            ctx.add_artifact(
                "source_pdf",
                dest_path,
                kind="pdf",
                metadata={
                    "invoice_number": normalized_record.get("invoice_number", ""),
                    "source_file": original_name,
                },
            )

        logger.info(
            "Wrote invoice %s to %s",
            normalized_record.get("invoice_number", "unknown"),
            output_csv,
        )

    def _ensure_invoice_not_written(self, output_csv: str, invoice: dict) -> None:
        """Raise if the current CSV is unreadable or already has this invoice."""
        rows = self._read_csv_rows(output_csv)
        self._raise_if_duplicate(rows, str(invoice.get("invoice_number", "")))

    def _write_csv_record(self, output_csv: str, invoice: dict) -> None:
        """Append a single invoice record using an atomic CSV replacement."""
        rows = self._read_csv_rows(output_csv)
        invoice_number = str(invoice.get("invoice_number", ""))
        self._raise_if_duplicate(rows, invoice_number)
        rows.append(self._csv_row(invoice))
        self._replace_csv(output_csv, rows)

    def _read_csv_rows(self, output_csv: str) -> list[dict[str, str]]:
        """Read existing CSV rows, treating malformed output as retryable."""
        if not os.path.exists(output_csv):
            return []

        try:
            with open(output_csv, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != _CSV_HEADER:
                    raise csv.Error(f"Unexpected CSV header: {reader.fieldnames!r}")
                return [dict(row) for row in reader]
        except (csv.Error, OSError) as exc:
            raise SystemException(
                f"Could not read existing CSV output {output_csv}: {exc}",
                action=self.name,
            ) from exc

    def _replace_csv(self, output_csv: str, rows: list[dict[str, str]]) -> None:
        """Atomically replace the CSV with the supplied rows."""
        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=str(output_path.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temp_path, output_path)
        except OSError as exc:
            raise SystemException(
                f"Could not update CSV output {output_csv}: {exc}",
                action=self.name,
            ) from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _csv_row(self, invoice: dict) -> dict[str, str]:
        """Return a normalized CSV row for an invoice."""
        return {
            "invoice_number": str(invoice.get("invoice_number", "")),
            "date": str(invoice.get("date", "")),
            "vendor": str(invoice.get("vendor", "")),
            "line_items_count": str(
                invoice.get("line_items_count", len(invoice.get("line_items", [])))
            ),
            "subtotal": self._format_decimal(invoice.get("subtotal")),
            "total": self._format_decimal(invoice.get("total")),
            "currency": str(invoice.get("currency", "USD")),
        }

    def _raise_if_duplicate(self, rows: list[dict[str, str]], invoice_number: str) -> None:
        """Raise BusinessException when invoice_number already exists."""
        if not invoice_number:
            raise BusinessException(
                "Missing invoice number for output",
                action=self.name,
                stop=True,
            )
        for row in rows:
            if row.get("invoice_number") == invoice_number:
                raise BusinessException(
                    f"Duplicate invoice number: {invoice_number}",
                    action=self.name,
                    stop=True,
                )

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

        stem, ext = os.path.splitext(name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}{ext}")

        if not os.path.exists(dest_path):
            return dest_path

        counter = 1
        while True:
            dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}_{counter}{ext}")
            if not os.path.exists(dest_path):
                return dest_path
            counter += 1
