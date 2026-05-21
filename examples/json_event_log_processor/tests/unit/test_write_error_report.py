"""Unit tests for the WriteErrorReport skill."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from oref import SystemException
from skills.write_error_report import WriteErrorReport


class TestWriteErrorReport:
    """Test the WriteErrorReport skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_generates_report_with_failed_transactions(self, tmp_path):
        """Test that WriteErrorReport generates a report with failed transactions."""
        mock_tx = Mock()
        mock_tx.id = "tx-1"
        mock_tx.reference = "json-file-events_001"
        mock_tx.status.name = "SUCCESSFUL"
        mock_tx.retry_count = 0
        mock_skill = Mock()
        mock_skill.name = "validate_events"
        mock_skill.execution_order = 2
        mock_skill.exceptions = []
        mock_tx.skills = [mock_skill]
        mock_tx.ordered_skills = lambda: [mock_skill]

        mock_failed_tx = Mock()
        mock_failed_tx.id = "tx-2"
        mock_failed_tx.reference = "json-file-events_002"
        mock_failed_tx.status.name = "FAILED"
        mock_failed_tx.retry_count = 0
        mock_failed_skill = Mock()
        mock_failed_skill.name = "validate_events"
        mock_failed_skill.execution_order = 2
        mock_exc = Mock()
        mock_exc.__class__.__name__ = "BusinessException"
        mock_failed_skill.exceptions = [mock_exc]
        mock_failed_tx.skills = [mock_failed_skill]
        mock_failed_tx.ordered_skills = lambda: [mock_failed_skill]

        results_dir = str(tmp_path / "results")
        Path(results_dir).mkdir()

        self.mock_ctx.config = {"db_path": str(tmp_path / "oref.db"), "results_dir": results_dir}

        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.return_value = [mock_tx, mock_failed_tx]
            skill = WriteErrorReport("write_error_report", 1)
            skill.execute(self.mock_ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 2
        assert report["failed"] == 1
        assert len(report["failures"]) == 1
        assert report["failures"][0]["transaction_reference"] == "json-file-events_002"

    def test_handles_empty_transaction_list(self, tmp_path):
        """Test that WriteErrorReport handles empty transaction lists."""
        results_dir = str(tmp_path / "results")
        Path(results_dir).mkdir()

        self.mock_ctx.config = {"db_path": str(tmp_path / "oref.db"), "results_dir": results_dir}

        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.return_value = []
            skill = WriteErrorReport("write_error_report", 1)
            skill.execute(self.mock_ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["failed"] == 0

    def test_raises_on_db_read_failure(self, tmp_path):
        """Test that WriteErrorReport raises SystemException on DB read failure."""
        results_dir = str(tmp_path / "results")
        Path(results_dir).mkdir()

        self.mock_ctx.config = {"db_path": str(tmp_path / "nonexistent.db"), "results_dir": results_dir}

        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.side_effect = sqlite3.Error("DB error")
            skill = WriteErrorReport("write_error_report", 1)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "Failed to read transactions" in str(exc_info.value)
