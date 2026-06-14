"""Unit tests for WriteOutput skill."""

from __future__ import annotations

import csv
import os

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction

from skills.write_output import WriteOutput

class TestWriteOutput:
    """Tests for WriteOutput skill."""

    def _make_normalized_record(self, **overrides):
        base = {
            "invoice_number": "INV-2024-001",
            "date": "2024-01-15",
            "vendor": "ACME CORP",
            "line_items": [
                {"description": "widget a", "quantity": 10.0, "unit_price": 15.0},
                {"description": "widget b", "quantity": 5.0, "unit_price": 20.0},
            ],
            "line_items_count": 2,
            "subtotal": 250.00,
            "total": 250.00,
            "currency": "USD",
        }
        base.update(overrides)
        return base

    def _run_skill(self, record=None, file_path="/nonexistent/file.pdf", original_name=None, config=None):
        if record is None:
            record = self._make_normalized_record()
        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = record
        tx.state["file_path"] = file_path
        if original_name is not None:
            tx.state["original_name"] = original_name
        ctx = ProcessContext(transaction=tx, config=config or {})
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)
        return tx

    def test_write_output_csv_writing(self, tmp_env: str):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        tx = self._run_skill(config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})
        assert tx.state.get("output_written") is True

        assert os.path.exists(output_csv)
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["invoice_number"] == "INV-2024-001"
            assert row["date"] == "2024-01-15"
            assert row["vendor"] == "ACME CORP"
            assert row["line_items_count"] == "2"
            assert row["total"] == "250.00"
            assert row["currency"] == "USD"

    def test_write_output_multiple_records(self, tmp_env: str):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        cfg = {"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv}

        self._run_skill(record=self._make_normalized_record(invoice_number="INV-001"), config=cfg)
        self._run_skill(record=self._make_normalized_record(invoice_number="INV-002"), config=cfg)

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["invoice_number"] == "INV-001"
            assert rows[1]["invoice_number"] == "INV-002"

    def test_write_output_header_handling(self, tmp_env: str):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        self._run_skill(config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})

        with open(output_csv, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert lines[0].strip() == "invoice_number,date,vendor,line_items_count,subtotal,total,currency"
            assert "INV-2024-001" in lines[1]

    def test_write_output_decimal_formatting(self, tmp_env: str):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        self._run_skill(
            record=self._make_normalized_record(total=250.1, subtotal=100.0051),
            config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv},
        )

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["total"] == "250.10"
            assert row["subtotal"] == "100.01"

    def test_write_output_missing_normalized_record(self, tmp_env: str):
        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["file_path"] = "/nonexistent/file.pdf"
        ctx = ProcessContext(transaction=tx, config={})
        skill = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="normalized_record"):
            skill.execute(ctx)

    def test_write_output_missing_file_path(self, tmp_env: str):
        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        ctx = ProcessContext(transaction=tx, config={})
        skill = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="file_path"):
            skill.execute(ctx)

    def test_write_output_file_move_to_done(self, tmp_env: str):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        pdf_path = tmp_env / "sample_data" / "test.pdf"
        pdf_path.write_text("fake pdf content")

        tx = self._run_skill(
            file_path=str(pdf_path),
            original_name="test.pdf",
            config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv},
        )

        done_path = tmp_env / "sample_data" / "done" / "test.pdf"
        assert done_path.exists()
        assert not pdf_path.exists()

    def test_write_output_duplicate_detection(self, tmp_env: str):
        """Test that duplicate invoice numbers raise BusinessException."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        cfg = {"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv}

        # Write first record
        self._run_skill(config=cfg)

        # Try to write duplicate — should raise BusinessException
        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        tx.state["file_path"] = "/nonexistent/file.pdf"
        ctx = ProcessContext(transaction=tx, config=cfg)
        skill = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(BusinessException, match="Duplicate invoice number"):
            skill.execute(ctx)

    def test_write_output_blank_invoice_number_is_business_failure(self, tmp_env: str):
        """Blank invoice numbers should not bypass duplicate protection."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        with pytest.raises(BusinessException, match="Missing invoice number"):
            self._run_skill(
                record=self._make_normalized_record(invoice_number=""),
                config={
                    "sample_data_dir": sample_data_dir,
                    "results_dir": results_dir,
                    "output_csv": output_csv,
                },
            )

    def test_write_output_move_failure_does_not_append_csv(self, tmp_env: str, monkeypatch):
        """A retryable move failure must not leave a duplicate CSV record behind."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        pdf_path = tmp_env / "sample_data" / "locked.pdf"
        pdf_path.write_text("fake pdf content", encoding="utf-8")

        def fail_move(src, dst):
            raise OSError("locked")

        monkeypatch.setattr("skills.write_output.shutil.move", fail_move)

        with pytest.raises(SystemException, match="Failed to move PDF"):
            self._run_skill(
                file_path=str(pdf_path),
                original_name="locked.pdf",
                config={
                    "sample_data_dir": sample_data_dir,
                    "results_dir": results_dir,
                    "output_csv": output_csv,
                },
            )

        assert pdf_path.exists()
        assert not os.path.exists(output_csv)

    def test_write_output_retry_after_csv_failure_keeps_source_pdf_artifact(
        self, tmp_env: str, monkeypatch
    ):
        """A moved PDF path is durable so retry can register the source artifact."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        pdf_path = tmp_env / "sample_data" / "invoice.pdf"
        pdf_path.write_text("fake pdf content", encoding="utf-8")

        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        tx.state["file_path"] = str(pdf_path)
        tx.state["original_name"] = "invoice.pdf"
        ctx = ProcessContext(
            transaction=tx,
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)

        def fail_replace(output_csv, rows):
            raise SystemException("csv unavailable", action=skill.name)

        monkeypatch.setattr(skill, "_replace_csv", fail_replace)
        with pytest.raises(SystemException, match="csv unavailable"):
            skill.execute(ctx)

        done_path = tx.state["done_path"]
        assert not pdf_path.exists()
        assert os.path.exists(done_path)

        monkeypatch.undo()
        retry_skill = WriteOutput(name="write_output", execution_order=1)
        retry_skill.execute(ctx)

        artifact_paths = [artifact.path for artifact in tx.artifacts]
        assert done_path in artifact_paths

    def test_write_output_corrupt_csv_is_retryable(self, tmp_env: str):
        """Malformed CSV output should not bypass duplicate detection."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            f.write("not,the,expected,header\n")

        with pytest.raises(SystemException, match="Could not read existing CSV"):
            self._run_skill(
                config={
                    "sample_data_dir": sample_data_dir,
                    "results_dir": results_dir,
                    "output_csv": output_csv,
                }
            )

    def test_write_output_validation_skip(self, tmp_env: str):
        """Test that write_output skips if a validation backstop reaches it."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        tx = Transaction(reference="test", skills=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        tx.state["file_path"] = "/nonexistent/file.pdf"
        tx.state["validation_failed"] = True
        ctx = ProcessContext(transaction=tx, config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)
        assert tx.state.get("output_written") is None
        assert not os.path.exists(output_csv)
