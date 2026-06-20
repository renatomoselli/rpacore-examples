"""Unit tests for scan_inbox plain function."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rpacore import SqliteQueue, SystemException

from main import scan_inbox

class TestScanInbox:
    """Tests for the scan_inbox plain function."""

    def test_scan_inbox_pdf_discovery(self, tmp_env: Path):
        """Test that PDF files are discovered and enqueued."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        for i in range(3):
            (Path(sample_data_dir) / f"invoice_{i:03d}.pdf").write_text("fake pdf")

        queue = MagicMock()
        queue.add_once = MagicMock(return_value=True)
        config = {"sample_data_dir": sample_data_dir}

        result = scan_inbox(config, queue)

        assert result == 3
        assert queue.add_once.call_count == 3

    def test_scan_inbox_empty_inbox(self, tmp_env: Path):
        """Test that empty inbox returns 0."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        queue = MagicMock()
        queue.add_once = MagicMock(return_value=True)
        config = {"sample_data_dir": sample_data_dir}

        result = scan_inbox(config, queue)

        assert result == 0
        queue.add_once.assert_not_called()

    def test_scan_inbox_skip_subdirectories(self, tmp_env: Path):
        """Test that PDFs in done/ or failed/ subdirectories are skipped."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)
        done_dir = Path(sample_data_dir) / "done"
        done_dir.mkdir(exist_ok=True)

        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")
        (done_dir / "invoice_002.pdf").write_text("fake pdf")

        queue = MagicMock()
        queue.add_once = MagicMock(return_value=True)
        config = {"sample_data_dir": sample_data_dir}

        result = scan_inbox(config, queue)

        assert result == 1

    def test_scan_inbox_missing_directory(self, tmp_env: Path):
        """Test that missing inbox directory raises SystemException."""
        queue = MagicMock()
        config = {"sample_data_dir": "/nonexistent/path"}

        with pytest.raises(SystemException, match="does not exist"):
            scan_inbox(config, queue)

    def test_scan_inbox_payload_structure(self, tmp_env: Path):
        """Test that queue items have correct payload structure."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)
        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")

        queue = MagicMock()
        queue.add_once = MagicMock(return_value=True)
        config = {"sample_data_dir": sample_data_dir}

        scan_inbox(config, queue)

        call_args = queue.add_once.call_args
        item = call_args[0][0]
        assert item.payload["file_path"] == os.path.join(sample_data_dir, "invoice_001.pdf")
        assert item.payload["original_name"] == "invoice_001.pdf"
        assert item.reference == "invoice_001"

    def test_scan_inbox_hidden_files_skipped(self, tmp_env: Path):
        """Test that hidden files (starting with .) are skipped."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)

        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")
        (Path(sample_data_dir) / ".DS_Store.pdf").write_text("fake pdf")

        queue = MagicMock()
        queue.add_once = MagicMock(return_value=True)
        config = {"sample_data_dir": sample_data_dir}

        result = scan_inbox(config, queue)

        assert result == 1

    def test_scan_inbox_idempotent_enqueue(self, tmp_env: Path):
        """Test that add_once returns False for duplicate references."""
        sample_data_dir = str(tmp_env / "sample_data")
        os.makedirs(sample_data_dir, exist_ok=True)
        (Path(sample_data_dir) / "invoice_001.pdf").write_text("fake pdf")
        (Path(sample_data_dir) / "invoice_002.pdf").write_text("fake pdf")

        queue = MagicMock()
        # First file adds successfully, second is duplicate
        queue.add_once = MagicMock(side_effect=[True, False])
        config = {"sample_data_dir": sample_data_dir}

        result = scan_inbox(config, queue)

        assert result == 1  # Only 1 newly added
        assert queue.add_once.call_count == 2  # Both files attempted
