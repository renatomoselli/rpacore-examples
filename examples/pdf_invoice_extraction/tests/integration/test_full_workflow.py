"""Integration tests for the full PDF invoice extraction workflow."""

from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path

import pytest

from rpacore import (
    Engine,
    EnvCredentialProvider,
    ProcessContext,
    QueueItem,
    SqliteQueue,
    SystemException,
    Transaction,
    run_queue_loop,
)

from skills.open_pdf import OpenPdf
from skills.parse_invoice import ParseInvoice
from skills.validate_invoice import ValidateInvoice
from skills.normalize_record import NormalizeRecord
from skills.write_output import WriteOutput
from skills.scan_inbox import ScanInbox


def _create_sample_pdf(pdf_path: Path, text: str) -> None:
    """Create a sample PDF with extractable text using reportlab.

    Each line of ``text`` is drawn at a separate Y position so pdfplumber
    can extract them as distinct lines.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        width, height = letter
        y = height - 50
        for line in text.split("\n"):
            c.drawString(100, y, line)
            y -= 20
            if y < 50:
                c.showPage()
                y = height - 50
        c.save()
    except ImportError:
        # Fallback: create a minimal PDF
        pdf_path.write_bytes(b"%PDF-1.0\n%%EOF\n")


def _build_transaction(item: QueueItem) -> Transaction:
    """Build a transaction for each queued PDF invoice."""
    return Transaction(
        reference=f"invoice-{item.payload.get('original_name', 'unknown')}",
        skills=[
            OpenPdf(name="open_pdf", execution_order=1),
            ParseInvoice(name="parse_invoice", execution_order=2),
            ValidateInvoice(name="validate_invoice", execution_order=3),
            NormalizeRecord(name="normalize_record", execution_order=4),
            WriteOutput(name="write_output", execution_order=5),
        ],
    )


# Invoice texts with line items so validation passes
_INVOICE_001 = (
    "Invoice Number: INV-2024-001\n"
    "Date: 2024-01-15\n"
    "Bill From: Acme Corp\n"
    "Widget A 10 $15.00\n"
    "Widget B 5 $20.00\n"
    "Total: $250.00"
)

_INVOICE_002 = (
    "Invoice Number: INV-2024-002\n"
    "Date: 2024-02-20\n"
    "Bill From: Global Supplies\n"
    "Service B 4 $50.00\n"
    "Total: $200.00"
)

_INVOICE_003 = (
    "Invoice Number: INV-2024-003\n"
    "Date: 2024-03-10\n"
    "Bill From: Tech Solutions\n"
    "Service C 3 $100.00\n"
    "Total: $300.00"
)


class TestFullWorkflow:
    """Integration tests for the full queue-driven workflow."""

    def test_full_successful_workflow(self, tmp_env: str):
        """Test the full pipeline: scan -> queue -> process -> CSV output."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Create a sample PDF with invoice text including line items
        pdf_path = Path(sample_data_dir) / "invoice_001.pdf"
        _create_sample_pdf(pdf_path, _INVOICE_001)

        # Initialize queue
        config = {
            "max_retries": 2,
            "log_level": "WARNING",
            "db_path": str(tmp_env / "queue.db"),
            "sample_data_dir": sample_data_dir,
            "results_dir": results_dir,
            "output_csv": output_csv,
            "max_pages": 100,
        }
        queue = SqliteQueue(config)
        engine = Engine(max_retries=2)

        # Scan inbox
        scan_ctx = ProcessContext(
            transaction=Transaction(reference="scan-inbox", skills=[]),
            config=config,
            data={},
        )
        scan_skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": queue},
        )
        scan_skill.execute(scan_ctx)
        assert scan_ctx.data["scanned_count"] == 1

        # Run queue loop
        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=_build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
        )

        # Verify results
        assert result.completed == 1
        assert result.failed == 0

        # Verify CSV output
        assert os.path.exists(output_csv)
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["invoice_number"] == "INV-2024-001"
            assert rows[0]["vendor"] == "ACME CORP"
            assert rows[0]["total"] == "250.00"

        # Verify file moved to done/
        done_path = Path(sample_data_dir) / "done" / "invoice_001.pdf"
        assert done_path.exists()

    def test_full_workflow_empty_queue(self, tmp_env: str):
        """Test that empty queue produces no output."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        config = {
            "max_retries": 2,
            "log_level": "WARNING",
            "db_path": str(tmp_env / "queue.db"),
            "sample_data_dir": sample_data_dir,
            "results_dir": results_dir,
            "output_csv": os.path.join(results_dir, "output.csv"),
            "max_pages": 100,
        }
        queue = SqliteQueue(config)
        engine = Engine(max_retries=2)

        scan_ctx = ProcessContext(
            transaction=Transaction(reference="scan-inbox", skills=[]),
            config=config,
            data={},
        )
        scan_skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": queue},
        )
        scan_skill.execute(scan_ctx)

        assert scan_ctx.data["scanned_count"] == 0

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=_build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
        )

        assert result.completed == 0
        assert result.failed == 0

    def test_full_workflow_failed_validation(self, tmp_env: str):
        """Test that validation failures are handled correctly.

        An empty PDF (no extractable text) should fail validation and the
        source PDF should remain in sample_data/ (no failed/ folder disposition).
        """
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Create an empty PDF that will fail validation (no text -> no invoice data)
        pdf_path = Path(sample_data_dir) / "empty.pdf"
        pdf_path.write_bytes(b"%PDF-1.0\n%%EOF\n")

        config = {
            "max_retries": 2,
            "log_level": "WARNING",
            "db_path": str(tmp_env / "queue.db"),
            "sample_data_dir": sample_data_dir,
            "results_dir": results_dir,
            "output_csv": output_csv,
            "max_pages": 100,
        }
        queue = SqliteQueue(config)
        engine = Engine(max_retries=2)

        scan_ctx = ProcessContext(
            transaction=Transaction(reference="scan-inbox", skills=[]),
            config=config,
            data={},
        )
        scan_skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": queue},
        )
        scan_skill.execute(scan_ctx)
        assert scan_ctx.data["scanned_count"] == 1

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=_build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
        )

        # The empty PDF should fail (no text to parse)
        # With max_retries=2, the engine retries twice, so failed >= 1
        assert result.failed >= 1

        # Source PDF should remain in sample_data/ (no failed/ disposition)
        assert pdf_path.exists()

        # No CSV output should be written
        assert not os.path.exists(output_csv)

    def test_full_workflow_retry_on_system_exception(self, tmp_env: str):
        """Test that transient failures are retried.

        Uses a skill that fails once then succeeds, verifying that
        SystemException triggers retry and the transaction eventually completes.
        """
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Create a valid PDF with line items
        pdf_path = Path(sample_data_dir) / "invoice_001.pdf"
        _create_sample_pdf(pdf_path, _INVOICE_001)

        config = {
            "max_retries": 2,
            "log_level": "WARNING",
            "db_path": str(tmp_env / "queue.db"),
            "sample_data_dir": sample_data_dir,
            "results_dir": results_dir,
            "output_csv": output_csv,
            "max_pages": 100,
        }
        queue = SqliteQueue(config)
        engine = Engine(max_retries=2)

        scan_ctx = ProcessContext(
            transaction=Transaction(reference="scan-inbox", skills=[]),
            config=config,
            data={},
        )
        scan_skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": queue},
        )
        scan_skill.execute(scan_ctx)

        # Track retry count
        retry_count = [0]

        class FailingOpenPdf(OpenPdf):
            """OpenPdf that fails on first attempt, succeeds on retry."""

            def execute(self, ctx: ProcessContext) -> None:
                retry_count[0] += 1
                if retry_count[0] == 1:
                    raise SystemException("Transient failure", action=self.name)
                super().execute(ctx)

        def build_transaction_with_retry(item: QueueItem) -> Transaction:
            return Transaction(
                reference=f"invoice-{item.payload.get('original_name', 'unknown')}",
                skills=[
                    FailingOpenPdf(name="open_pdf", execution_order=1),
                    ParseInvoice(name="parse_invoice", execution_order=2),
                    ValidateInvoice(name="validate_invoice", execution_order=3),
                    NormalizeRecord(name="normalize_record", execution_order=4),
                    WriteOutput(name="write_output", execution_order=5),
                ],
            )

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=build_transaction_with_retry,
            config=config,
            credentials=EnvCredentialProvider(),
        )

        # Should succeed after retry
        assert result.completed == 1
        assert result.failed == 0
        assert retry_count[0] == 2  # Failed once, succeeded on retry

    def test_full_workflow_multiple_invoices(self, tmp_env: str):
        """Test processing multiple invoices in a single run."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        invoices = [
            ("invoice_001.pdf", _INVOICE_001),
            ("invoice_002.pdf", _INVOICE_002),
            ("invoice_003.pdf", _INVOICE_003),
        ]

        for name, text in invoices:
            pdf_path = Path(sample_data_dir) / name
            _create_sample_pdf(pdf_path, text)

        config = {
            "max_retries": 2,
            "log_level": "WARNING",
            "db_path": str(tmp_env / "queue.db"),
            "sample_data_dir": sample_data_dir,
            "results_dir": results_dir,
            "output_csv": output_csv,
            "max_pages": 100,
        }
        queue = SqliteQueue(config)
        engine = Engine(max_retries=2)

        scan_ctx = ProcessContext(
            transaction=Transaction(reference="scan-inbox", skills=[]),
            config=config,
            data={},
        )
        scan_skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": queue},
        )
        scan_skill.execute(scan_ctx)
        assert scan_ctx.data["scanned_count"] == 3

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=_build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
        )

        assert result.completed == 3
        assert result.failed == 0

        # Verify CSV has 3 records
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3
            invoice_numbers = {row["invoice_number"] for row in rows}
            assert invoice_numbers == {"INV-2024-001", "INV-2024-002", "INV-2024-003"}
