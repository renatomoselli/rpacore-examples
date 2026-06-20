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

from main import scan_inbox, build_transaction
from skills.open_pdf import OpenPdf
from skills.parse_invoice import ParseInvoice
from skills.validate_invoice import ValidateInvoice
from skills.normalize_record import NormalizeRecord
from skills.write_output import WriteOutput

def _create_sample_pdf(pdf_path: Path, text: str) -> None:
    """Create a deterministic text-backed PDF fixture."""
    pdf_path.write_text(text, encoding="utf-8")

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

def _make_config(tmp_env: Path, **overrides) -> dict:
    """Build a test config dict with migrated keys."""
    sample_data_dir = str(tmp_env / "sample_data")
    results_dir = str(tmp_env / "results")
    config = {
        "max_retries": 2,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_env / "rpacore.db"),
        "sample_data_dir": sample_data_dir,
        "results_dir": results_dir,
        "output_csv": os.path.join(results_dir, "output.csv"),
        "max_pages": 100,
        "queue": {
            "db_path": str(tmp_env / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }
    config.update(overrides)
    return config

class TestFullWorkflow:
    """Integration tests for the full queue-driven workflow."""

    def test_full_successful_workflow(self, tmp_env: Path):
        """Test the full pipeline: scan -> queue -> process -> CSV output."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        pdf_path = Path(sample_data_dir) / "invoice_001.pdf"
        _create_sample_pdf(pdf_path, _INVOICE_001)

        config = _make_config(tmp_env)
        queue = SqliteQueue(config["queue"])
        engine = Engine(max_retries=2)

        scanned = scan_inbox(config, queue)
        assert scanned == 1

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
            transaction_db_path=str(config["transaction_db_path"]),
        )

        assert result.completed == 1
        assert result.failed == 0

        assert os.path.exists(output_csv)
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["invoice_number"] == "INV-2024-001"
            assert rows[0]["vendor"] == "ACME CORP"
            assert rows[0]["total"] == "250.00"

        done_path = Path(sample_data_dir) / "done" / "invoice_001.pdf"
        assert done_path.exists()

    def test_full_workflow_empty_queue(self, tmp_env: Path):
        """Test that empty queue produces no output."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        config = _make_config(tmp_env)
        queue = SqliteQueue(config["queue"])
        engine = Engine(max_retries=2)

        scanned = scan_inbox(config, queue)
        assert scanned == 0

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
            transaction_db_path=str(config["transaction_db_path"]),
        )

        assert result.completed == 0
        assert result.failed == 0

    def test_full_workflow_failed_validation(self, tmp_env: Path):
        """Test that validation failures are handled correctly."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        pdf_path = Path(sample_data_dir) / "empty.pdf"
        pdf_path.write_bytes(b"%PDF-1.0\n%%EOF\n")

        config = _make_config(tmp_env)
        queue = SqliteQueue(config["queue"])
        engine = Engine(max_retries=2)

        scanned = scan_inbox(config, queue)
        assert scanned == 1

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
            transaction_db_path=str(config["transaction_db_path"]),
        )

        assert result.failed >= 1
        assert pdf_path.exists()
        assert not os.path.exists(output_csv)

    def test_full_workflow_retry_on_system_exception(self, tmp_env: Path):
        """Test that transient failures are retried."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        pdf_path = Path(sample_data_dir) / "invoice_001.pdf"
        _create_sample_pdf(pdf_path, _INVOICE_001)

        config = _make_config(tmp_env)
        queue = SqliteQueue(config["queue"])
        engine = Engine(max_retries=2)

        scanned = scan_inbox(config, queue)
        assert scanned == 1

        retry_count = [0]

        class FailingOpenPdf(OpenPdf):
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
            transaction_db_path=str(config["transaction_db_path"]),
        )

        assert result.completed == 1
        assert result.failed == 0
        assert retry_count[0] == 2

    def test_full_workflow_multiple_invoices(self, tmp_env: Path):
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

        config = _make_config(tmp_env)
        queue = SqliteQueue(config["queue"])
        engine = Engine(max_retries=2)

        scanned = scan_inbox(config, queue)
        assert scanned == 3

        result = run_queue_loop(
            queue=queue,
            engine=engine,
            build_transaction=build_transaction,
            config=config,
            credentials=EnvCredentialProvider(),
            transaction_db_path=str(config["transaction_db_path"]),
        )

        assert result.completed == 3
        assert result.failed == 0

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 3
            invoice_numbers = {row["invoice_number"] for row in rows}
            assert invoice_numbers == {"INV-2024-001", "INV-2024-002", "INV-2024-003"}
