from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from oref import (
    Engine,
    EnvCredentialProvider,
    QueueItem,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    run_queue_loop,
    save_transaction,
)

from skills.append_to_master import AppendToMaster
from skills.compute_derived_fields import ComputeDerivedFields
from skills.move_file import MoveFile
from skills.read_report_file import ReadReportFile
from skills.validate_schema import ValidateSchema

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("inbox_dir", str),
        ("done_dir", str),
        ("failed_dir", str),
        ("master_csv", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )

    queue_config = config.get("queue")
    if not isinstance(queue_config, dict):
        raise SystemException("Missing required [queue] config section", action="main")


def scan_inbox(config: dict, queue: SqliteQueue) -> int:
    """Add new CSV files in the inbox as queue items."""
    inbox = Path(str(config["inbox_dir"]))
    if not inbox.exists():
        raise SystemException(f"Inbox directory does not exist: {inbox}", action="scan_inbox")

    existing_refs = _active_queue_references(queue)
    count = 0
    for csv_file in sorted(inbox.glob("*.csv")):
        reference = f"branch-report-{csv_file.stem}"
        if reference in existing_refs:
            continue
        queue.add(
            QueueItem(
                reference=reference,
                payload={"file_path": str(csv_file)},
            )
        )
        count += 1
    return count


def build_transaction(item: QueueItem) -> Transaction:
    return Transaction(
        reference=item.reference,
        skills=[
            ReadReportFile(name="read_report_file", execution_order=1),
            ValidateSchema(name="validate_schema", execution_order=2),
            ComputeDerivedFields(name="compute_derived_fields", execution_order=3),
            AppendToMaster(name="append_to_master", execution_order=4),
            MoveFile(name="move_file", execution_order=5),
        ],
    )


def _active_queue_references(queue: SqliteQueue) -> set[str]:
    """Return queue references that are not terminal yet."""
    conn = sqlite3.connect(queue.db_path)
    try:
        rows = conn.execute(
            "SELECT reference FROM queue_items WHERE status IN ('pending', 'in_progress')"
        ).fetchall()
    finally:
        conn.close()
    return {str(row[0]) for row in rows}


def _move_failed_file(item: QueueItem, config: dict) -> None:
    file_path = item.payload.get("file_path")
    failed_dir = config.get("failed_dir")
    if not isinstance(file_path, str) or not isinstance(failed_dir, str):
        return

    src = Path(file_path)
    if not src.exists():
        return

    dst_dir = Path(failed_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst_dir / src.name))


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    for key in ("done_dir", "failed_dir"):
        Path(str(config[key])).mkdir(parents=True, exist_ok=True)
    Path(str(config["master_csv"])).parent.mkdir(parents=True, exist_ok=True)

    queue = SqliteQueue(config["queue"])
    enqueued = scan_inbox(config, queue)
    logger.info("Enqueued %d CSV file(s).", enqueued)

    engine = Engine(max_retries=int(config["max_retries"]))

    def after_item(item: QueueItem, transaction: Transaction | None, error: Exception | None) -> None:
        if transaction is not None:
            save_transaction(transaction, db_path=str(config["db_path"]))
            if transaction.status is not Status.SUCCESSFUL:
                _move_failed_file(item, config)
        elif error is not None:
            _move_failed_file(item, config)

    summary = run_queue_loop(
        queue,
        engine,
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="file-inbox-worker",
        logger=logger,
        after_item=after_item,
    )

    logger.info(
        "Queue run complete. processed=%d completed=%d failed=%d callback_errors=%d",
        summary.processed,
        summary.completed,
        summary.failed,
        summary.callback_errors,
    )


if __name__ == "__main__":
    main()
