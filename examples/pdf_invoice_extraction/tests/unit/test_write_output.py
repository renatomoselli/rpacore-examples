"""Unit tests for WriteOutput skill."""

from __future__ import annotations

import csv
import os

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from skills.write_output import WriteOutput


class TestWriteOutput:
    """Tests for WriteOutput skill."""

    def _make_normalized_record(self, **overrides):
        """Create a valid normalized record dict with optional overrides."""
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

    def test_write_output_csv_writing(self, tmp_env: str):
        """Test that a normalized record is written to CSV."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={
                "normalized_record": record,
                "file_path": "/nonexistent/file.pdf",
            },
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)

        assert ctx.data.get("output_written") is True

        # Verify CSV content
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
        """Test that multiple records are appended to CSV."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        record1 = self._make_normalized_record(invoice_number="INV-001")
        record2 = self._make_normalized_record(invoice_number="INV-002")

        # Write first record
        ctx1 = ProcessContext(
            transaction=Transaction(reference="test1", skills=[]),
            data={"normalized_record": record1, "file_path": "/nonexistent/file.pdf"},
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx1)

        # Write second record
        record2_copy = dict(record2)
        ctx2 = ProcessContext(
            transaction=Transaction(reference="test2", skills=[]),
            data={"normalized_record": record2_copy, "file_path": "/nonexistent/file2.pdf"},
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill.execute(ctx2)

        # Verify both records
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert rows[0]["invoice_number"] == "INV-001"
            assert rows[1]["invoice_number"] == "INV-002"

    def test_write_output_header_handling(self, tmp_env: str):
        """Test that CSV header is written only for the first record."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"normalized_record": record, "file_path": "/nonexistent/file.pdf"},
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)

        with open(output_csv, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # First line should be the header
            assert lines[0].strip() == "invoice_number,date,vendor,line_items_count,subtotal,total,currency"
            # Second line should be the data
            assert "INV-2024-001" in lines[1]

    def test_write_output_decimal_formatting(self, tmp_env: str):
        """Test that decimal values are formatted to 2 places."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        record = self._make_normalized_record(total=250.1, subtotal=100.0051)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"normalized_record": record, "file_path": "/nonexistent/file.pdf"},
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)

        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            assert row["total"] == "250.10"
            assert row["subtotal"] == "100.01"

    def test_write_output_missing_normalized_record(self, tmp_env: str):
        """Test that missing normalized_record raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"file_path": "/nonexistent/file.pdf"},
        )
        skill = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="normalized_record"):
            skill.execute(ctx)

    def test_write_output_missing_file_path(self, tmp_env: str):
        """Test that missing file_path raises SystemException."""
        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"normalized_record": record},
        )
        skill = WriteOutput(name="write_output", execution_order=1)

        with pytest.raises(SystemException, match="file_path"):
            skill.execute(ctx)

    def test_write_output_file_move_to_done(self, tmp_env: str):
        """Test that source PDF is moved to done/ folder."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Create a source PDF
        pdf_path = tmp_env / "sample_data" / "test.pdf"
        pdf_path.write_text("fake pdf content")

        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={
                "normalized_record": record,
                "file_path": str(pdf_path),
                "original_name": "test.pdf",
            },
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)

        # Verify file moved
        done_path = tmp_env / "sample_data" / "done" / "test.pdf"
        assert done_path.exists()
        assert not pdf_path.exists()

    def test_write_output_duplicate_detection(self, tmp_env: str):
        """Test that duplicate filenames get a timestamp suffix."""
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Create a source PDF in sample_data
        pdf_path = tmp_env / "sample_data" / "test.pdf"
        pdf_path.write_text("fake pdf content")
        # Also create a file in done/ with the same name
        done_dir = tmp_env / "sample_data" / "done"
        done_dir.mkdir(parents=True, exist_ok=True)
        (done_dir / "test.pdf").write_text("existing")

        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={
                "normalized_record": record,
                "file_path": str(pdf_path),
                "original_name": "test.pdf",
            },
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        skill.execute(ctx)

        # Should have created a unique file
        done_files = list(done_dir.glob("test_*"))
        assert len(done_files) == 1

    def test_write_output_validation_skip(self, tmp_env: str):
        """Test that validation failure short-circuits before write_output."""
        # This is tested indirectly: if validation fails, normalize_record
        # raises SystemException, so write_output never runs.
        # Here we verify that write_output doesn't have its own validation check.
        sample_data_dir = str(tmp_env / "sample_data")
        results_dir = str(tmp_env / "results")
        output_csv = os.path.join(results_dir, "output.csv")
        os.makedirs(sample_data_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        record = self._make_normalized_record()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={
                "normalized_record": record,
                "file_path": "/nonexistent/file.pdf",
                "validation_failed": True,  # This should NOT be checked by write_output
            },
            config={
                "sample_data_dir": sample_data_dir,
                "results_dir": results_dir,
                "output_csv": output_csv,
            },
        )
        skill = WriteOutput(name="write_output", execution_order=1)
        # Should write normally — validation_failed is not checked here
        skill.execute(ctx)
        assert ctx.data.get("output_written") is True
