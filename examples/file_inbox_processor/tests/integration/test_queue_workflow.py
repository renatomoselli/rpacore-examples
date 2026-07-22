from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from threading import Event

import pytest

import main as file_inbox_main
from rpacore import (
    BusinessException,
    Engine,
    EnvCredentialProvider,
    ProcessContext,
    QueueItem,
    QueueStatus,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    run_queue_loop,
)

from main import _move_failed_file_safely, build_transaction, scan_inbox
from skills.append_to_master import AppendToMaster
from skills.read_report_file import ReadReportFile


def test_queue_workflow_processes_valid_files_and_moves_invalid_file(tmp_path):
    inbox = tmp_path / "inbox"
    done = tmp_path / "done"
    failed = tmp_path / "failed"
    output = tmp_path / "output"
    inbox.mkdir()

    (inbox / "valid.csv").write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    (inbox / "invalid.csv").write_text(
        "branch_id,date,revenue,headcount\n205,2024-03-01,8950.00,0\n",
        encoding="utf-8",
    )

    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(inbox),
        "done_dir": str(done),
        "failed_dir": str(failed),
        "master_csv": str(output / "master_consolidated.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }
    queue = SqliteQueue(config["queue"])
    assert scan_inbox(config, queue) == 2

    def after_item(item: QueueItem, transaction, error):
        if transaction is not None:
            if transaction.status is not Status.SUCCESSFUL:
                _move_failed_file_safely(item, config)
        elif error is not None:
            _move_failed_file_safely(item, config)

    summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="test-worker",
        after_item=after_item,
        transaction_db_path=str(config["transaction_db_path"]),
    )

    assert summary.processed == 2
    assert summary.completed == 1
    assert summary.failed == 1
    assert (done / "valid.csv").exists()
    assert (failed / "invalid.csv").exists()

    with Path(config["master_csv"]).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "branch_id": "101",
            "date": "2024-03-01",
            "revenue": "12450.75",
            "headcount": "23",
            "source_file": "valid.csv",
            "revenue_per_headcount": "541.34",
        }
    ]

    valid_item = queue.get_item(next_item_id(queue, "branch-report-valid"))
    invalid_item = queue.get_item(next_item_id(queue, "branch-report-invalid"))
    assert valid_item is not None
    assert invalid_item is not None
    assert valid_item.status == QueueStatus.SUCCESSFUL
    assert invalid_item.status == QueueStatus.FAILED


def test_scan_inbox_does_not_enqueue_duplicate_active_items(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "branch_101.csv").write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    config = {
        "inbox_dir": str(inbox),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }
    queue = SqliteQueue(config["queue"])

    assert scan_inbox(config, queue) == 1
    assert scan_inbox(config, queue) == 0

    assert count_queue_items(queue, "branch-report-branch_101") == 1


def test_business_validation_failure_does_not_add_system_failure(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    inbox_file = inbox / "invalid.csv"
    inbox_file.write_text(
        "branch_id,date,revenue,headcount\n205,2024-03-01,8950.00,0\n",
        encoding="utf-8",
    )
    config = {
        "inbox_dir": str(inbox),
        "done_dir": str(tmp_path / "done"),
        "master_csv": str(tmp_path / "output" / "master.csv"),
    }
    tx = build_transaction(
        QueueItem(
            reference="branch-report-invalid",
            payload={"file_path": str(inbox_file)},
        )
    )

    # Seed state from payload.
    tx.state["file_path"] = str(inbox_file)
    Engine(max_retries=1).run(ProcessContext(transaction=tx, config=config))

    failed = tx.failed_skills()
    assert len(failed) == 1
    assert failed[0].name == "validate_schema"
    assert isinstance(failed[0].exceptions[-1], BusinessException)
    assert not Path(config["master_csv"]).exists()
    assert inbox_file.exists()


def test_path_traversal_fails_before_business_validation(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside_file = tmp_path / "outside.csv"
    outside_file.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    config = {
        "inbox_dir": str(inbox),
        "done_dir": str(tmp_path / "done"),
        "master_csv": str(tmp_path / "output" / "master.csv"),
    }
    tx = build_transaction(
        QueueItem(
            reference="branch-report-outside",
            payload={"file_path": str(outside_file)},
        )
    )

    tx.state["file_path"] = str(outside_file)
    Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config))

    failed = tx.failed_skills()
    assert len(failed) == 1
    assert failed[0].name == "read_report_file"
    assert isinstance(failed[0].exceptions[-1], SystemException)
    assert "resolves outside root" in str(failed[0].exceptions[-1]).lower()
    assert not Path(config["master_csv"]).exists()
    assert outside_file.exists()


def test_master_append_is_idempotent_by_source_file(tmp_path):
    master_csv = tmp_path / "master.csv"
    state = {
        "report_file": str(tmp_path / "valid.csv"),
        "processed_report": {
            "branch_id": 101,
            "date": "2024-03-01",
            "revenue": "12450.75",
            "headcount": 23,
            "revenue_per_headcount": "541.34",
        },
    }
    config = {"master_csv": str(master_csv)}
    for _ in range(2):
        skill = AppendToMaster(name="append_to_master", execution_order=1)
        tx = Transaction(reference="append", skills=[skill])
        # Seed state from payload.
        for key, value in state.items():
            tx.state[key] = value
        Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config))

    with master_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["source_file"] == "valid.csv"


def test_stale_lease_is_reclaimed_by_next_worker(tmp_path):
    queue = SqliteQueue(
        {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 1,
            "max_retries": 1,
        }
    )
    item = QueueItem(
        reference="branch-report-stale",
        payload={"file_path": str(tmp_path / "inbox" / "stale.csv")},
    )
    assert queue.add_once(item)

    claimed = queue.next_item(worker_id="worker-1")
    assert claimed is not None
    assert claimed.id == item.id
    assert claimed.status == QueueStatus.IN_PROGRESS

    stale_claimed_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    mark_claim_stale(queue, item.id, stale_claimed_at)

    reclaimed = queue.next_item(worker_id="worker-2")
    assert reclaimed is not None
    assert reclaimed.id == item.id
    assert reclaimed.status == QueueStatus.IN_PROGRESS
    assert reclaimed.claimed_by == "worker-2"


def test_failed_file_outside_inbox_is_not_moved(tmp_path):
    inbox = tmp_path / "inbox"
    failed = tmp_path / "failed"
    inbox.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("branch_id,date,revenue,headcount\n101,2024-03-01,1,1\n", encoding="utf-8")

    _move_failed_file_safely(
        QueueItem(reference="branch-report-outside", payload={"file_path": str(outside)}),
        {"inbox_dir": str(inbox), "failed_dir": str(failed)},
    )

    assert outside.exists()
    assert not (failed / outside.name).exists()


def test_main_retries_source_before_terminal_failed_file_disposition(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    done = tmp_path / "done"
    failed = tmp_path / "failed"
    inbox.mkdir()
    source = inbox / "retry.csv"
    source.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "log_format": "text",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(inbox),
        "done_dir": str(done),
        "failed_dir": str(failed),
        "master_csv": str(tmp_path / "output" / "master.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 1,
        },
    }
    original_execute = ReadReportFile.execute
    attempts = 0

    def fail_once(self, ctx):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SystemException("temporary read failure", action=self.name)
        return original_execute(self, ctx)

    monkeypatch.setattr(file_inbox_main, "_load_example_config", lambda: config)
    monkeypatch.setattr(file_inbox_main, "configure_logger", lambda **_kwargs: file_inbox_main.logger)
    monkeypatch.setattr(ReadReportFile, "execute", fail_once)

    file_inbox_main.main()

    item = SqliteQueue(config["queue"]).list_items()[0]
    assert attempts == 2
    assert item.status == QueueStatus.SUCCESSFUL
    assert not source.exists()
    assert (done / source.name).exists()
    assert not (failed / source.name).exists()


def test_main_moves_terminal_business_failure_to_failed(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    done = tmp_path / "done"
    failed = tmp_path / "failed"
    inbox.mkdir()
    source = inbox / "invalid.csv"
    source.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,0\n",
        encoding="utf-8",
    )
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "log_format": "text",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(inbox),
        "done_dir": str(done),
        "failed_dir": str(failed),
        "master_csv": str(tmp_path / "output" / "master.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 1,
        },
    }

    monkeypatch.setattr(file_inbox_main, "_load_example_config", lambda: config)
    monkeypatch.setattr(file_inbox_main, "configure_logger", lambda **_kwargs: file_inbox_main.logger)

    file_inbox_main.main()

    item = SqliteQueue(config["queue"]).list_items()[0]
    assert item.status == QueueStatus.FAILED
    assert not source.exists()
    assert not (done / source.name).exists()
    assert (failed / source.name).exists()


def test_retry_resumes_same_bound_transaction_without_duplicate_append(tmp_path):
    inbox = tmp_path / "inbox"
    done = tmp_path / "done"
    failed = tmp_path / "failed"
    output = tmp_path / "output"
    inbox.mkdir()
    report_file = inbox / "retry.csv"
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(inbox),
        "done_dir": str(done),
        "failed_dir": str(failed),
        "master_csv": str(output / "master_consolidated.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "lease_timeout": 30,
            "max_retries": 1,
        },
    }
    queue = SqliteQueue(config["queue"])
    item = QueueItem(
        reference="branch-report-retry",
        payload={"file_path": str(report_file)},
    )
    assert queue.add_once(item)

    stop_after_first_attempt = Event()
    first_summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="test-worker-1",
        after_item=lambda _item, _transaction, _error: stop_after_first_attempt.set(),
        stop_event=stop_after_first_attempt,
        transaction_db_path=str(config["transaction_db_path"]),
    )
    retriable_item = queue.get_item(item.id)
    assert first_summary.processed == 1
    assert first_summary.completed == 0
    assert first_summary.failed == 1
    assert retriable_item is not None
    assert retriable_item.status == QueueStatus.PENDING
    assert retriable_item.transaction_id

    report_file.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )

    second_summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="test-worker-2",
        transaction_db_path=str(config["transaction_db_path"]),
    )
    completed_item = queue.get_item(item.id)
    assert second_summary.processed == 1
    assert second_summary.completed == 1
    assert second_summary.failed == 0
    assert completed_item is not None
    assert completed_item.status == QueueStatus.SUCCESSFUL
    assert completed_item.transaction_id == retriable_item.transaction_id
    assert (done / "retry.csv").exists()

    with Path(config["master_csv"]).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["source_file"] == "retry.csv"


def test_failed_file_move_error_is_logged_without_raising(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    failed = tmp_path / "failed"
    inbox.mkdir()
    src = inbox / "invalid.csv"
    src.write_text(
        "branch_id,date,revenue,headcount\n205,2024-03-01,8950.00,0\n",
        encoding="utf-8",
    )
    item = QueueItem(
        reference="branch-report-invalid",
        payload={"file_path": str(src)},
    )

    def fail_move(*args, **kwargs):
        raise OSError("destination unavailable")

    monkeypatch.setattr(file_inbox_main.shutil, "move", fail_move)

    _move_failed_file_safely(
        item,
        {
            "inbox_dir": str(inbox),
            "failed_dir": str(failed),
        },
    )

    assert src.exists()
    assert not (failed / "invalid.csv").exists()


def next_item_id(queue: SqliteQueue, reference: str) -> str:
    """Get queue item ID by reference (test-only SQL helper)."""
    conn = sqlite3.connect(queue.db_path)
    try:
        row = conn.execute(
            "SELECT id FROM queue_items WHERE reference = ?",
            (reference,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


def count_queue_items(queue: SqliteQueue, reference: str) -> int:
    """Count queue items by reference (test-only SQL helper)."""
    conn = sqlite3.connect(queue.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM queue_items WHERE reference = ?",
            (reference,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0])


def mark_claim_stale(queue: SqliteQueue, item_id: str, claimed_at: datetime) -> None:
    """Move claimed_at backward for deterministic lease-reclaim coverage."""
    conn = sqlite3.connect(queue.db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE queue_items SET claimed_at = ? WHERE id = ?",
                (claimed_at.isoformat(), item_id),
            )
    finally:
        conn.close()
