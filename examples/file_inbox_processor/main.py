from __future__ import annotations

import shutil
from pathlib import Path

from rpacore import (
    ConfigField,
    Engine,
    EnvCredentialProvider,
    QueueItem,
    QueueRunSummary,
    QueueStatus,
    SqliteQueue,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_path,
    resolve_config_paths,
    run_queue_loop,
    validate_config,
)

from skills.append_to_master import AppendToMaster
from skills.compute_derived_fields import ComputeDerivedFields
from skills.move_file import MoveFile
from skills.read_report_file import ReadReportFile
from skills.validate_schema import ValidateSchema

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_FORMATS = ("text", "json")
PATH_KEYS = (
    "transaction_db_path",
    "inbox_dir",
    "done_dir",
    "failed_dir",
    "master_csv",
    "queue.db_path",
)
CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, choices=LOG_LEVELS),
    ConfigField("log_format", str, choices=LOG_FORMATS),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("inbox_dir", str, allow_empty=False),
    ConfigField("done_dir", str, allow_empty=False),
    ConfigField("failed_dir", str, allow_empty=False),
    ConfigField("master_csv", str, allow_empty=False),
    ConfigField("queue.db_path", str, allow_empty=False),
    ConfigField("queue.lease_timeout", int, min_value=1),
    ConfigField("queue.max_retries", int, min_value=0),
)


def _validate_config(config: dict[str, object]) -> dict[str, object]:
    """Validate configuration and contain configured paths under ``PROJECT_ROOT``."""
    try:
        validate_config(config, CONFIG_FIELDS)
        return resolve_config_paths(
            config,
            PATH_KEYS,
            base_dir=PROJECT_ROOT,
            root=PROJECT_ROOT,
        )
    except SystemException:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc


def _load_example_config() -> dict[str, object]:
    return _validate_config(load_config(PROJECT_ROOT / "config.toml", require_file=True))


def _log_queue_summary(summary: QueueRunSummary) -> None:
    fields = (
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
    logger.info(
        "Queue run complete.",
        extra={
            "event": "file_inbox_run_summary",
            **{field: getattr(summary, field) for field in fields},
        },
    )


def scan_inbox(config: dict, queue: SqliteQueue) -> int:
    """Add new CSV files in the inbox as queue items."""
    inbox = Path(str(config["inbox_dir"]))
    if not inbox.exists():
        raise SystemException(f"Inbox directory does not exist: {inbox}", action="scan_inbox")

    count = 0
    for csv_file in sorted(inbox.glob("*.csv")):
        reference = f"branch-report-{csv_file.stem}"
        added = queue.add_once(
            QueueItem(
                reference=reference,
                payload={"file_path": str(csv_file)},
            )
        )
        if added:
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


def _move_failed_file(item: QueueItem, config: dict) -> None:
    file_path = item.payload.get("file_path")
    failed_dir = config.get("failed_dir")
    if not isinstance(file_path, str) or not isinstance(failed_dir, str):
        logger.warning("Cannot move failed file: file_path=%r, failed_dir=%r", file_path, failed_dir)
        return

    inbox_dir = config.get("inbox_dir")
    if isinstance(inbox_dir, str) and inbox_dir:
        try:
            src = Path(
                resolve_config_path(
                    file_path,
                    base_dir=inbox_dir,
                    root=inbox_dir,
                    key="move_failed_file",
                )
            )
        except SystemException:
            logger.warning("Invalid source file path: %s", file_path)
            return
    else:
        src = Path(file_path)

    if not src.exists():
        return

    dst_dir = Path(failed_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst_dir / src.name))


def _move_failed_file_safely(item: QueueItem, config: dict) -> None:
    try:
        _move_failed_file(item, config)
    except Exception:
        logger.exception("Unable to move failed file for queue item %s", item.id)


def main() -> None:
    config = _load_example_config()
    configure_logger(
        level=str(config["log_level"]),
        fmt=str(config["log_format"]),
        json_version=2,
    )

    for key in ("done_dir", "failed_dir"):
        Path(str(config[key])).mkdir(parents=True, exist_ok=True)
    Path(str(config["master_csv"])).parent.mkdir(parents=True, exist_ok=True)

    queue = SqliteQueue(config["queue"])
    enqueued = scan_inbox(config, queue)
    logger.info("Enqueued %d CSV file(s).", enqueued)

    engine = Engine(max_retries=int(config["max_retries"]))

    summary = run_queue_loop(
        queue,
        engine,
        build_transaction,
        config,
        EnvCredentialProvider(),
        worker_id="file-inbox-worker",
        logger=logger,
        transaction_db_path=str(config["transaction_db_path"]),
    )

    for failed_item in queue.list_items(statuses=(QueueStatus.FAILED,)):
        _move_failed_file_safely(failed_item, config)

    _log_queue_summary(summary)


if __name__ == "__main__":
    main()
