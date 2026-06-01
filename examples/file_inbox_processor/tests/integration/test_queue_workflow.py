from __future__ import annotations

import csv
from pathlib import Path

from rpacore import (
    BusinessException,
    Engine,
    EnvCredentialProvider,
    ProcessContext,
    QueueItem,
    QueueStatus,
    SqliteQueue,
    Status,
    Transaction,
    run_queue_loop,
)

from main import _move_failed_file, build_transaction, save_transaction, scan_inbox
from skills.append_to_master import AppendToMaster


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
        "db_path": str(tmp_path / "rpacore.db"),
        "inbox_dir": str(inbox),
        "done_dir": str(done),
        "failed_dir": str(failed),
        "master_csv": str(output / "master_consolidated.csv"),
        "queue": {
            "db_path": str(tmp_path / "queue.db"),
            "claim_timeout": 30,
            "max_retries": 0,
        },
    }
    queue = SqliteQueue(config["queue"])
    assert scan_inbox(config, queue) == 2

    def after_item(item: QueueItem, transaction, error):
        if transaction is not None:
            save_transaction(transaction, db_path=str(config["db_path"]))
            if transaction.status is not Status.SUCCESSFUL:
                _move_failed_file(item, config)
        elif error is not None:
            _move_failed_file(item, config)

    summary = run_queue_loop(
        queue,
        Engine(max_retries=0),
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="test-worker",
        after_item=after_item,
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
            "claim_timeout": 30,
            "max_retries": 0,
        },
    }
    queue = SqliteQueue(config["queue"])

    assert scan_inbox(config, queue) == 1
    assert scan_inbox(config, queue) == 0

    assert count_queue_items(queue, "branch-report-branch_101") == 1


def test_business_validation_failure_does_not_add_system_failure(tmp_path):
    inbox_file = tmp_path / "invalid.csv"
    inbox_file.write_text(
        "branch_id,date,revenue,headcount\n205,2024-03-01,8950.00,0\n",
        encoding="utf-8",
    )
    config = {
        "done_dir": str(tmp_path / "done"),
        "master_csv": str(tmp_path / "output" / "master.csv"),
    }
    tx = build_transaction(
        QueueItem(
            reference="branch-report-invalid",
            payload={"file_path": str(inbox_file)},
        )
    )

    Engine(max_retries=1).run(ProcessContext(transaction=tx, config=config, data={"file_path": str(inbox_file)}))

    failed = tx.failed_skills()
    assert len(failed) == 1
    assert failed[0].name == "validate_schema"
    assert isinstance(failed[0].exceptions[-1], BusinessException)
    assert not Path(config["master_csv"]).exists()
    assert inbox_file.exists()


def test_master_append_is_idempotent_by_source_file(tmp_path):
    master_csv = tmp_path / "master.csv"
    data = {
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
        Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config, data=data))

    with master_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["source_file"] == "valid.csv"


def next_item_id(queue: SqliteQueue, reference: str) -> str:
    import sqlite3

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
    import sqlite3

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
