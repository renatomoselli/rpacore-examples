from __future__ import annotations

"""Unit tests for the WriteErrorReport skill."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from rpacore import (
    BusinessException,
    ProcessContext,
    Status,
    SystemException,
    Transaction,
    save_transaction,
)

from skills.write_error_report import WriteErrorReport, _iter_run_transactions


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
                "run_id": "test-run",
            },
        )

    def test_generates_report_with_failed_transactions(self) -> None:
        from rpacore import Skill as RpaSkill
        mock_tx = Transaction(
            reference="ok",
            status=Status.SUCCESSFUL,
            metadata={"run_id": "test-run"},
        )
        failed_skill = RpaSkill(name="validate_events", execution_order=2)
        failed_skill.exceptions = [BusinessException("Validation error", stop=True)]
        mock_failed_tx = Transaction(
            reference="fail",
            status=Status.FAILED,
            skills=[failed_skill],
            metadata={"run_id": "test-run"},
        )

        results_dir = self.ctx.config["results_dir"]

        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.return_value = iter([mock_tx, mock_failed_tx])
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 2
        assert report["failed"] == 1
        assert len(report["failures"]) == 1
        assert report["failures"][0]["transaction_reference"] == "fail"
        assert len(self.transaction.artifacts) == 1
        artifact = self.transaction.artifacts[0]
        assert artifact.name == "error_report.json"
        assert artifact.kind == "report"
        assert artifact.metadata["total_transactions"] == 2
        assert artifact.metadata["failed_count"] == 1
        assert artifact.metadata["persistence_error_count"] == 0

    def test_handles_empty_transaction_list(self) -> None:
        results_dir = self.ctx.config["results_dir"]

        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.return_value = iter(())
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(results_dir) / "error_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["failed"] == 0
        assert report["unresolved"] == 0
        assert report["persistence_error_count"] == 0
        assert report["persistence_errors"] == []

    def test_includes_persistence_errors_from_current_run(self) -> None:
        self.ctx.config["persistence_errors"] = [
            {
                "transaction_reference": "json-file-events_001",
                "transaction_id": "tx-1",
                "status": "SUCCESSFUL",
                "exception_type": "OSError",
                "message": "disk full",
            },
        ]

        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.return_value = iter(())
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(self.ctx.config["results_dir"]) / "error_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["failed"] == 0
        assert report["persistence_error_count"] == 1
        assert report["persistence_errors"][0]["transaction_reference"] == "json-file-events_001"
        assert self.transaction.metadata["persistence_error_count"] == 1

    def test_non_list_persistence_errors_are_treated_as_empty(self) -> None:
        self.ctx.config["persistence_errors"] = {"bad": "shape"}

        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.return_value = iter(())
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(self.ctx.config["results_dir"]) / "error_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["persistence_error_count"] == 0
        assert report["persistence_errors"] == []
        assert self.transaction.metadata["persistence_error_count"] == 0

    def test_only_failed_status_counts_as_failed(self) -> None:
        transactions = [
            Transaction(reference="pending", status=Status.PENDING, metadata={"run_id": "test-run"}),
            Transaction(reference="in-progress", status=Status.IN_PROGRESS, metadata={"run_id": "test-run"}),
            Transaction(reference="failed", status=Status.FAILED, metadata={"run_id": "test-run"}),
            Transaction(reference="ok", status=Status.SUCCESSFUL, metadata={"run_id": "test-run"}),
        ]

        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.return_value = iter(transactions)
            skill = WriteErrorReport("write_error_report", 5)
            skill.execute(self.ctx)

        report_path = Path(self.ctx.config["results_dir"]) / "error_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["total_transactions"] == 4
        assert report["successful"] == 1
        assert report["failed"] == 1
        assert report["unresolved"] == 2
        assert [failure["transaction_reference"] for failure in report["failures"]] == ["failed"]
        assert self.transaction.metadata["unresolved_count"] == 2

    def test_write_failure_reports_target_path_without_name_error(self) -> None:
        with patch("skills.write_error_report.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = OSError("cannot create results")
            with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
                mock_transactions.return_value = iter(())
                skill = WriteErrorReport("write_error_report", 5)
                with pytest.raises(SystemException) as exc_info:
                    skill.execute(self.ctx)

        message = str(exc_info.value)
        assert "error_report.json" in message
        assert "cannot create results" in message

    def test_raises_on_db_read_failure(self) -> None:
        with patch("skills.write_error_report._iter_run_transactions") as mock_transactions:
            mock_transactions.side_effect = sqlite3.Error("DB error")
            skill = WriteErrorReport("write_error_report", 5)
            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.ctx)
            assert "Failed to read transactions" in str(exc_info.value)

    def test_raises_system_exception_for_malformed_query_page(self) -> None:
        db_path = self.ctx.config["transaction_db_path"]
        save_transaction(
            Transaction(reference="existing", metadata={"run_id": "test-run"}),
            db_path=db_path,
        )
        malformed_page = SimpleNamespace(transactions=(), has_more=True, next_cursor=None)

        with patch("skills.write_error_report.query_transactions", return_value=malformed_page):
            with pytest.raises(SystemException, match="omitted its continuation cursor"):
                WriteErrorReport("write_error_report", 5).execute(self.ctx)

    def test_logs_when_a_selected_transaction_is_removed_before_loading(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "rpacore.db")
        transaction = Transaction(reference="removed", metadata={"run_id": "test-run"})
        save_transaction(transaction, db_path=db_path)

        with patch("skills.write_error_report.load_transaction", side_effect=KeyError(transaction.id)):
            with patch("skills.write_error_report.logger.warning") as mock_warning:
                assert list(_iter_run_transactions(db_path, "test-run")) == []

        mock_warning.assert_called_once_with(
            "Transaction %s was removed before error-report details could be loaded",
            transaction.id,
        )

    def test_logs_when_the_empty_batch_has_no_transaction_database(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "missing-rpacore.db")

        with patch("skills.write_error_report.logger.info") as mock_info:
            assert list(_iter_run_transactions(db_path, "test-run")) == []

        mock_info.assert_called_once_with(
            "No transaction database exists at %s; writing an empty report for run %s",
            db_path,
            "test-run",
        )

    def test_requires_run_id(self) -> None:
        self.ctx.config.pop("run_id")

        with pytest.raises(SystemException) as exc_info:
            WriteErrorReport("write_error_report", 5).execute(self.ctx)

        assert "run_id" in str(exc_info.value)

    def test_filters_report_to_current_run(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "rpacore.db")
        results_dir = tmp_path / "results"
        results_dir.mkdir(exist_ok=True)

        save_transaction(
            Transaction(
                reference="run-1-ok",
                status=Status.SUCCESSFUL,
                metadata={"run_id": "run-1"},
            ),
            db_path=db_path,
        )
        save_transaction(
            Transaction(
                reference="run-1-failed",
                status=Status.FAILED,
                metadata={"run_id": "run-1"},
            ),
            db_path=db_path,
        )
        save_transaction(
            Transaction(
                reference="error-report",
                status=Status.SUCCESSFUL,
                metadata={"run_id": "run-1", "transaction_kind": "error-report"},
            ),
            db_path=db_path,
        )
        save_transaction(
            Transaction(
                reference="run-2-ok",
                status=Status.SUCCESSFUL,
                metadata={"run_id": "run-2"},
            ),
            db_path=db_path,
        )

        report_tx = Transaction(reference="error-report", state={"run_id": "run-2"})
        ctx = ProcessContext(
            transaction=report_tx,
            config={
                "transaction_db_path": db_path,
                "results_dir": str(results_dir),
            },
        )

        WriteErrorReport("write_error_report", 5).execute(ctx)

        report = json.loads((results_dir / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 1
        assert report["successful"] == 1
        assert report["failed"] == 0
        assert report["unresolved"] == 0
        assert report["failures"] == []

    def test_includes_run_older_than_the_legacy_global_100_record_window(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "rpacore.db")
        results_dir = tmp_path / "results"
        results_dir.mkdir(exist_ok=True)
        created_at = datetime(2026, 7, 18, tzinfo=timezone.utc)

        save_transaction(
            Transaction(
                reference="older-current-run",
                status=Status.FAILED,
                created_at=created_at,
                metadata={"run_id": "current-run"},
            ),
            db_path=db_path,
        )
        for index in range(100):
            save_transaction(
                Transaction(
                    reference=f"newer-other-run-{index}",
                    status=Status.SUCCESSFUL,
                    created_at=created_at + timedelta(minutes=index + 1),
                    metadata={"run_id": "other-run"},
                ),
                db_path=db_path,
            )

        ctx = ProcessContext(
            transaction=Transaction(reference="error-report", state={"run_id": "current-run"}),
            config={
                "transaction_db_path": db_path,
                "results_dir": str(results_dir),
            },
        )

        WriteErrorReport("write_error_report", 5).execute(ctx)

        report = json.loads((results_dir / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 1
        assert report["failed"] == 1
        assert report["failures"][0]["transaction_reference"] == "older-current-run"
