"""Unit tests for the WriteErrorReport skill."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlite3

from rpacore import BusinessException, ProcessContext, Status, SystemException, Transaction

from skills.write_error_report import WriteErrorReport


class TestWriteErrorReport:
    """Test the WriteErrorReport skill."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        db_path = str(tmp_path / "rpacore.db")
        self.transaction = Transaction(reference="test")
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={
                "transaction_db_path": db_path,
                "results_dir": str(results_dir),
            },
        )

    def test_generates_report_with_failed_transactions(self) -> None:
        from rpacore import Skill as RpaSkill
        mock_tx = Transaction(reference="ok", status=Status.SUCCESSFUL)
        failed_skill = RpaSkill(name="validate_events", execution_order=2)
        failed_skill.exceptions = [BusinessException("Validation error", stop=True)]
        mock_failed_tx = Transaction(reference="fail", status=Status.FAILED, skills=[failed_skill])

        results_dir = self.ctx.config["results_dir"]

        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.return_value = [mock_tx, mock_failed_tx]
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 2
        assert report["failed"] == 1
        assert len(report["failures"]) == 1
        assert report["failures"][0]["transaction_reference"] == "fail"

    def test_handles_empty_transaction_list(self) -> None:
        results_dir = self.ctx.config["results_dir"]

        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.return_value = []
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["failed"] == 0

    def test_raises_on_db_read_failure(self) -> None:
        with patch("skills.write_error_report.list_transactions") as mock_list:
            mock_list.side_effect = sqlite3.Error("DB error")
            skill = WriteErrorReport("write_error_report", 5)
            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.ctx)
            assert "Failed to read transactions" in str(exc_info.value)
