"""Unit tests for WriteOutput step."""

from __future__ import annotations

import csv
import os
import shutil
import time

import pytest

from rpacore import BusinessException, ProcessContext, Status, SystemException, Transaction

from steps.write_output import WriteOutput, _output_csv_lock

class TestWriteOutput:
    """Tests for WriteOutput step."""

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

    def _run_step(self, record=None, file_path="/nonexistent/file.pdf", original_name=None, config=None):
        if record is None:
            record = self._make_normalized_record()
        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = record
        tx.state["file_path"] = file_path
        if original_name is not None:
            tx.state["original_name"] = original_name
        ctx = ProcessContext(transaction=tx, config=config or {})
        step = WriteOutput(name="write_output", execution_order=1)
        step.execute(ctx)
        return tx

    def test_write_output_csv_writing(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        tx = self._run_step(config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})
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

    def test_write_output_multiple_records(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        cfg = {"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv}

        self._run_step(record=self._make_normalized_record(invoice_number="INV-001"), config=cfg)
        self._run_step(record=self._make_normalized_record(invoice_number="INV-002"), config=cfg)

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["invoice_number"] == "INV-001"
            assert rows[1]["invoice_number"] == "INV-002"

    def test_write_output_holds_lock_during_csv_update(self, tmp_env: Path, monkeypatch):
        output_csv = tmp_env / "results" / "output.csv"
        original_write = WriteOutput._write_csv_record

        def assert_locked(self, path, invoice, rows=None):
            assert output_csv.with_name("output.csv.lock").exists()
            return original_write(self, path, invoice, rows)

        monkeypatch.setattr(WriteOutput, "_write_csv_record", assert_locked)
        self._run_step(
            config={
                "sample_data_dir": str(tmp_env / "sample_data"),
                "results_dir": str(output_csv.parent),
                "output_csv": str(output_csv),
            }
        )

        assert output_csv.exists()
        assert not output_csv.with_name("output.csv.lock").exists()

    def test_write_output_header_handling(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        self._run_step(config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})

        with open(output_csv, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert lines[0].strip() == "invoice_number,date,vendor,line_items_count,subtotal,total,currency"
            assert "INV-2024-001" in lines[1]

    def test_write_output_decimal_formatting(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        self._run_step(
            record=self._make_normalized_record(total=250.1, subtotal=100.0051),
            config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv},
        )

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["total"] == "250.10"
            assert row["subtotal"] == "100.01"

    def test_write_output_escapes_spreadsheet_formula_prefixes(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        self._run_step(
            record=self._make_normalized_record(
                invoice_number="=cmd|' /C calc'!A0",
                date="+2024-01-15",
                vendor="@ACME",
                subtotal=-10.0,
                total=-10.0,
                currency="-USD",
            ),
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )

        with open(output_csv, "r", encoding="utf-8", newline="") as f:
            row = next(csv.DictReader(f))

        assert row["invoice_number"] == "'=cmd|' /C calc'!A0"
        assert row["date"] == "'+2024-01-15"
        assert row["vendor"] == "'@ACME"
        assert row["subtotal"] == "'-10.00"
        assert row["total"] == "'-10.00"
        assert row["currency"] == "'-USD"

    def test_write_output_missing_normalized_record(self, tmp_env: Path):
        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["file_path"] = "/nonexistent/file.pdf"
        ctx = ProcessContext(transaction=tx, config={})
        step = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="normalized_record"):
            step.execute(ctx)

    def test_write_output_missing_file_path(self, tmp_env: Path):
        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        ctx = ProcessContext(transaction=tx, config={})
        step = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="file_path"):
            step.execute(ctx)

    def test_write_output_file_move_to_done(self, tmp_env: Path):
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        pdf_path = tmp_env / "sample_data" / "test.pdf"
        pdf_path.write_text("fake pdf content")

        tx = self._run_step(
            file_path=str(pdf_path),
            original_name="test.pdf",
            config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv},
        )

        done_path = tmp_env / "sample_data" / "done" / "test.pdf"
        assert done_path.exists()
        assert not pdf_path.exists()

    def test_write_output_duplicate_detection(self, tmp_env: Path):
        """Test that duplicate invoice numbers raise BusinessException."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        cfg = {"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv}

        # Write first record
        self._run_step(config=cfg)

        # Try to write duplicate — should raise BusinessException
        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        tx.state["file_path"] = "/nonexistent/file.pdf"
        ctx = ProcessContext(transaction=tx, config=cfg)
        step = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(BusinessException, match="Duplicate invoice number"):
            step.execute(ctx)

    def test_write_output_blank_invoice_number_is_business_failure(self, tmp_env: Path):
        """Blank invoice numbers should not bypass duplicate protection."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        with pytest.raises(BusinessException, match="Missing invoice number"):
            self._run_step(
                record=self._make_normalized_record(invoice_number=""),
                config={
                    "sample_data_dir": sample_data_dir,
                    "results_dir": results_dir,
                    "output_csv": output_csv,
                },
            )

    def test_write_output_move_failure_does_not_append_csv(self, tmp_env: Path, monkeypatch):
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

        monkeypatch.setattr("steps.write_output.shutil.move", fail_move)

        with pytest.raises(SystemException, match="Failed to move PDF"):
            self._run_step(
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

    def test_write_output_csv_failure_restores_source_pdf_for_retry(
        self, tmp_env: Path, monkeypatch
    ):
        """A CSV failure after moving the PDF restores the source for retry."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        pdf_path = tmp_env / "sample_data" / "invoice.pdf"
        pdf_path.write_text("fake pdf content", encoding="utf-8")

        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
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
        step = WriteOutput(name="write_output", execution_order=1)

        def fail_replace(source, destination):
            raise OSError("csv unavailable")

        monkeypatch.setattr(os, "replace", fail_replace)
        with pytest.raises(SystemException, match="csv unavailable"):
            step.execute(ctx)

        assert pdf_path.exists()
        assert "done_path" not in tx.state
        assert not os.path.exists(output_csv)

        monkeypatch.undo()
        retry_step = WriteOutput(name="write_output", execution_order=1)
        retry_step.execute(ctx)

        done_path = tx.state["done_path"]
        artifact_paths = [artifact.path for artifact in tx.artifacts]
        assert done_path in artifact_paths

    def test_write_output_failed_restore_retains_recoverable_done_path(
        self, tmp_env: Path, monkeypatch
    ):
        sample_data_dir = tmp_env / "sample_data"
        output_csv = tmp_env / "results" / "output.csv"
        sample_data_dir.mkdir()
        pdf_path = sample_data_dir / "invoice.pdf"
        pdf_path.write_text("fake pdf content", encoding="utf-8")

        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state.update(
            normalized_record=self._make_normalized_record(),
            file_path=str(pdf_path),
            original_name="invoice.pdf",
        )
        ctx = ProcessContext(
            transaction=tx,
            config={
                "sample_data_dir": str(sample_data_dir),
                "results_dir": str(output_csv.parent),
                "output_csv": str(output_csv),
            },
        )
        step = WriteOutput(name="write_output", execution_order=1)
        original_move = shutil.move
        move_count = 0

        def fail_restore(source, destination):
            nonlocal move_count
            move_count += 1
            if move_count == 2:
                raise OSError("restore locked")
            return original_move(source, destination)

        def fail_replace(source, destination):
            raise OSError("csv unavailable")

        monkeypatch.setattr("steps.write_output.shutil.move", fail_restore)
        monkeypatch.setattr(os, "replace", fail_replace)

        with pytest.raises(SystemException, match="Failed to restore PDF"):
            step.execute(ctx)

        done_path = tx.state["done_path"]
        assert os.path.exists(done_path)
        assert not pdf_path.exists()

        monkeypatch.undo()
        WriteOutput(name="write_output", execution_order=1).execute(ctx)

        assert output_csv.exists()
        assert done_path in [artifact.path for artifact in tx.artifacts]

    def test_write_output_corrupt_csv_is_permanent_business_failure(self, tmp_env: Path):
        """Malformed CSV output should fail without technical retries."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            f.write("not,the,expected,header\n")

        with pytest.raises(BusinessException, match="Unexpected CSV header"):
            self._run_step(
                config={
                    "sample_data_dir": sample_data_dir,
                    "results_dir": results_dir,
                    "output_csv": output_csv,
                }
            )

    def test_write_output_validation_skip(self, tmp_env: Path):
        """Test that write_output skips if a validation backstop reaches it."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        tx = Transaction(reference="test", steps=[WriteOutput(name="write_output", execution_order=1)])
        tx.state["normalized_record"] = self._make_normalized_record()
        tx.state["file_path"] = "/nonexistent/file.pdf"
        tx.state["validation_failed"] = True
        ctx = ProcessContext(transaction=tx, config={"sample_data_dir": sample_data_dir, "results_dir": results_dir, "output_csv": output_csv})
        step = WriteOutput(name="write_output", execution_order=1)
        step.execute(ctx)
        assert step.status == Status.SKIPPED
        assert tx.state.get("output_written") is None
        assert not os.path.exists(output_csv)

    def test_output_lock_close_failure_still_removes_sidecar(self, tmp_env: Path, monkeypatch):
        output_csv = tmp_env / "results" / "output.csv"
        output_csv.parent.mkdir()
        real_close = os.close

        def fail_close(fd):
            real_close(fd)
            raise OSError("bad fd")

        monkeypatch.setattr("steps.write_output.os.close", fail_close)
        with _output_csv_lock(output_csv, action="test"):
            assert output_csv.with_name("output.csv.lock").exists()

        assert not output_csv.with_name("output.csv.lock").exists()

    def test_output_lock_recovers_stale_crash_sidecar(self, tmp_env: Path):
        output_csv = tmp_env / "results" / "output.csv"
        output_csv.parent.mkdir()
        lock_path = output_csv.with_name("output.csv.lock")
        lock_path.write_text("abandoned", encoding="utf-8")
        stale_time = time.time() - 61
        os.utime(lock_path, (stale_time, stale_time))

        with _output_csv_lock(output_csv, action="test"):
            assert lock_path.exists()
            assert lock_path.read_text(encoding="utf-8") == ""

        assert not lock_path.exists()

    def test_find_unique_dest_has_bounded_collision_search(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda path: True)

        with pytest.raises(SystemException, match="after 1000 attempts"):
            WriteOutput._find_unique_dest(str(tmp_path), "done", "invoice.pdf")
