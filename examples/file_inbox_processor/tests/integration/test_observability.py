"""Protected logging and read-only doctor coverage for File Inbox Processor."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import rpacore
from rpacore import (
    Engine,
    EnvCredentialProvider,
    QueueItem,
    SqliteQueue,
    configure_logger,
    run_queue_loop,
)

import main as file_inbox_main
from main import build_transaction, scan_inbox


SUMMARY_FIELDS = (
    "processed",
    "completed",
    "failed",
    "callback_errors",
    "persistence_errors",
    "lifecycle_errors",
    "notification_errors",
    "retry_scheduled",
    "terminal_failed",
    "lease_lost",
    "transition_unknown",
)
PROTECTED_ENVELOPE_FIELDS = {
    "log_format_version",
    "timestamp",
    "severity",
    "logger",
    "event",
    "message",
}


def _workflow_config(tmp_path: Path) -> dict[str, object]:
    return {
        "max_retries": 0,
        "log_level": "INFO",
        "log_format": "json",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(tmp_path / "inbox"),
        "done_dir": str(tmp_path / "done"),
        "failed_dir": str(tmp_path / "failed"),
        "master_csv": str(tmp_path / "output" / "master.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }


def _run_doctor(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    package_root = Path(rpacore.__file__).resolve().parent.parent
    env = os.environ.copy()
    existing_python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(package_root)
        if existing_python_path is None
        else str(package_root) + os.pathsep + existing_python_path
    )
    return subprocess.run(
        [sys.executable, "-m", "rpacore.cli", "doctor", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _database_snapshot(paths: tuple[Path, ...]) -> tuple[set[str], dict[Path, bytes]]:
    parent = paths[0].parent
    return ({path.name for path in parent.iterdir()}, {path: path.read_bytes() for path in paths if path.exists()})


def test_queue_run_emits_protected_v3_correlation_and_exact_summary(tmp_path):
    config = _workflow_config(tmp_path)
    inbox = Path(str(config["inbox_dir"]))
    inbox.mkdir()
    source = inbox / "branch_101.csv"
    source.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    queue = SqliteQueue(config["queue"])
    assert scan_inbox(config, queue) == 1

    stream = io.StringIO()
    configure_logger(level="INFO", fmt="json", stream=stream)
    summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="observability-worker",
        transaction_db_path=str(config["transaction_db_path"]),
    )
    file_inbox_main._log_queue_summary(summary)

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert records
    assert all(record["log_format_version"] == 3 for record in records)
    assert all(PROTECTED_ENVELOPE_FIELDS <= record.keys() for record in records)
    assert all(PROTECTED_ENVELOPE_FIELDS.isdisjoint(record["attributes"]) for record in records)
    assert str(inbox) not in stream.getvalue()

    step_started = next(record for record in records if record["event"] == "rpacore.step.started")
    correlation = step_started["attributes"]
    assert correlation["worker_id"] == "observability-worker"
    assert correlation["queue_item_id"]
    assert correlation["queue_reference"] == "branch-report-branch_101"
    assert correlation["transaction_id"]
    assert correlation["transaction_reference"] == "branch-report-branch_101"
    assert correlation["step_name"] == "read_report_file"
    assert correlation["step_execution_order"] == 1
    assert correlation["retry_count"] == 0
    assert "attempt_number" not in correlation

    summary_record = next(
        record for record in records if record["event"] == "rpacore.file.inbox.run.summary"
    )
    assert summary_record["attributes"] == {
        field: getattr(summary, field) for field in SUMMARY_FIELDS
    }
    assert "attempt_number" not in summary_record["attributes"]


def test_doctor_inspects_existing_workflow_databases_without_mutation(tmp_path):
    config = _workflow_config(tmp_path)
    inbox = Path(str(config["inbox_dir"]))
    inbox.mkdir()
    (inbox / "branch_101.csv").write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    queue = SqliteQueue(config["queue"])
    assert scan_inbox(config, queue) == 1
    summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="doctor-worker",
        transaction_db_path=str(config["transaction_db_path"]),
    )
    assert summary.completed == 1

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'transaction_db_path = "rpacore.db"\n[queue]\ndb_path = "queue.db"\n',
        encoding="utf-8",
    )
    transaction_db = Path(str(config["transaction_db_path"]))
    queue_db = Path(str(config["queue"]["db_path"]))  # type: ignore[index]
    database_paths = (
        transaction_db,
        Path(f"{transaction_db}-journal"),
        Path(f"{transaction_db}-wal"),
        Path(f"{transaction_db}-shm"),
        queue_db,
        Path(f"{queue_db}-journal"),
        Path(f"{queue_db}-wal"),
        Path(f"{queue_db}-shm"),
    )
    before_members, before_bytes = _database_snapshot(database_paths)

    result = _run_doctor(
        "--config",
        str(config_path),
        "--transaction-db",
        str(transaction_db),
        "--queue-db",
        str(queue_db),
        "--json",
        cwd=tmp_path,
    )

    after_members, after_bytes = _database_snapshot(database_paths)
    assert result.returncode == 0
    assert result.stderr == ""
    assert after_members == before_members
    assert after_bytes == before_bytes
    assert str(transaction_db) not in result.stdout
    assert str(queue_db) not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["doctor_format_version"] == 1
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["transactions.schema"]["status"] == "pass"
    assert checks["transactions.schema"]["details"]["version"] == 10
    assert checks["queue.schema"]["status"] == "pass"
    assert checks["queue.health"]["status"] == "pass"


@pytest.mark.parametrize(
    ("option", "check_id", "filename"),
    (
        ("--transaction-db", "transactions.schema", "missing-transactions.db"),
        ("--queue-db", "queue.schema", "missing-queue.db"),
    ),
)
def test_doctor_missing_explicit_database_fails_without_creation(tmp_path, option, check_id, filename):
    missing = tmp_path / filename

    result = _run_doctor(option, str(missing), "--json", cwd=tmp_path)

    assert result.returncode == 1
    assert result.stderr == ""
    assert not missing.exists()
    assert not Path(f"{missing}-journal").exists()
    assert not Path(f"{missing}-wal").exists()
    assert not Path(f"{missing}-shm").exists()
    assert str(missing) not in result.stdout
    checks = {check["id"]: check for check in json.loads(result.stdout)["checks"]}
    assert checks[check_id]["status"] == "fail"
