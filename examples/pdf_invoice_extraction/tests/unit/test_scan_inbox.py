"""Unit tests for ScanInbox skill."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from oref import ProcessContext, SystemException, Transaction

from skills.scan_inbox import ScanInbox


class TestScanInbox:
    """Tests for ScanInbox skill."""

    def test_scan_inbox_pdf_discovery(self, tmp_env: str, mock_queue: MagicMock):
        """Test that PDF files are discovered and enqueued."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        # Create sample PDF files
        for i in range(3):
            (Path(sample_data_dir) / f"invoice_{i:03d}.pdf").write_text("fake pdf")

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": sample_data_dir},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )
        skill.execute(ctx)

        assert ctx.data["scanned_count"] == 3
        assert mock_queue.add.call_count == 3

    def test_scan_inbox_empty_inbox(self, tmp_env: str, mock_queue: MagicMock):
        """Test that empty inbox sets scanned_count to 0."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": sample_data_dir},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )
        skill.execute(ctx)

        assert ctx.data["scanned_count"] == 0
        mock_queue.add.assert_not_called()

    def test_scan_inbox_skip_subdirectories(self, tmp_env: str, mock_queue: MagicMock):
        """Test that PDFs in done/ or failed/ subdirectories are skipped."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)
        done_dir = Path(sample_data_dir) / "done"
        done_dir.mkdir(exist_ok=True)

        # Create PDF in root
        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")
        # Create PDF in done/ (should be skipped)
        (done_dir / "invoice_002.pdf").write_text("fake pdf")

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": sample_data_dir},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )
        skill.execute(ctx)

        assert ctx.data["scanned_count"] == 1

    def test_scan_inbox_missing_queue(self, tmp_env: str):
        """Test that missing queue raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={},
        )

        with pytest.raises(SystemException, match="No queue"):
            skill.execute(ctx)

    def test_scan_inbox_payload_structure(self, tmp_env: str, mock_queue: MagicMock):
        """Test that queue items have correct payload structure."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)
        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": sample_data_dir},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )
        skill.execute(ctx)

        # Verify queue.add was called with QueueItem having correct payload
        call_args = mock_queue.add.call_args
        item = call_args[0][0]
        assert item.payload["file_path"] == os.path.join(sample_data_dir, "invoice_001.pdf")
        assert item.payload["original_name"] == "invoice_001.pdf"
        assert item.reference == "invoice_001"

    def test_scan_inbox_hidden_files_skipped(self, tmp_env: str, mock_queue: MagicMock):
        """Test that hidden files (starting with .) are skipped."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")
        (Path(sample_data_dir) / ".DS_Store.pdf").write_text("fake pdf")

        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": sample_data_dir},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )
        skill.execute(ctx)

        assert ctx.data["scanned_count"] == 1

    def test_scan_inbox_missing_directory(self, tmp_env: str, mock_queue: MagicMock):
        """Test that missing inbox directory raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
            config={"sample_data_dir": "/nonexistent/path"},
        )
        skill = ScanInbox(
            name="scan_inbox",
            execution_order=1,
            arguments={"queue": mock_queue},
        )

        with pytest.raises(SystemException, match="does not exist"):
            skill.execute(ctx)
