from __future__ import annotations

"""Unit tests for main.py helper functions."""

from pathlib import Path
from unittest.mock import patch

from rpacore import Engine, Transaction

from main import (
    _make_error_report_tx,
    _record_persistence_error,
    _run_error_report,
    _save_transaction_safely,
)
from steps.write_error_report import WriteErrorReport


def test_make_error_report_tx_sets_report_metadata() -> None:
    tx = _make_error_report_tx("run-1", report_attempt=2)

    assert tx.reference == "error-report"
    assert tx.state == {"run_id": "run-1"}
    assert tx.metadata["example"] == "json_event_log_processor"
    assert tx.metadata["run_id"] == "run-1"
    assert tx.metadata["transaction_kind"] == "error-report"
    assert tx.metadata["report_attempt"] == 2
    assert len(tx.steps) == 1
    assert isinstance(tx.steps[0], WriteErrorReport)


def test_record_persistence_error_appends_json_safe_details() -> None:
    config = {}
    tx = Transaction(reference="json-file-events_001")

    _record_persistence_error(config, tx, OSError("disk full"))

    assert config["persistence_errors"] == [
        {
            "transaction_reference": "json-file-events_001",
            "transaction_id": tx.id,
            "status": tx.status.name,
            "exception_type": "OSError",
            "message": "disk full",
        },
    ]


def test_save_transaction_safely_records_failure(tmp_path: Path) -> None:
    config = {}
    tx = Transaction(reference="json-file-events_001")

    with patch("main.save_transaction", side_effect=OSError("locked")):
        assert _save_transaction_safely(tx, str(tmp_path / "rpacore.db"), config) is False

    assert config["persistence_errors"][0]["transaction_reference"] == "json-file-events_001"
    assert config["persistence_errors"][0]["message"] == "locked"


def test_run_error_report_refreshes_after_persistence_failure(tmp_path: Path) -> None:
    config = {
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "results_dir": str(tmp_path / "results"),
        "run_id": "run-1",
    }
    engine = Engine(max_retries=0)
    calls = []

    def fake_save_transaction(tx, db_path):
        calls.append(tx.metadata["report_attempt"])
        if tx.metadata["report_attempt"] == 1:
            raise OSError("report persistence failed")

    with patch("main.save_transaction", side_effect=fake_save_transaction):
        _run_error_report(engine, config, config["transaction_db_path"], "run-1")

    assert calls == [1]
    assert config["persistence_errors"][0]["transaction_reference"] == "error-report"

    report = (tmp_path / "results" / "error_report.json").read_text(encoding="utf-8")
    assert "report persistence failed" in report
