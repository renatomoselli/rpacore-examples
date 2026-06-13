"""RPA Core orchestration for the Windows Calculator example.

Scans an input directory for CSV expression files, builds a transaction
per file, and runs the queue loop.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from rpacore import (
    Engine,
    QueueItem,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    run_queue_loop,
)

from skills.open_calculator import OpenCalculator
from skills.load_expressions import LoadExpressions
from skills.process_expressions import ProcessExpressions
from skills.write_report import WriteReport
from skills.close_calculator import CloseCalculator
from skills.move_file import MoveFile

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    for key, expected_type in (
        ("engine_max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
        ("input_dir", str),
        ("output_dir", str),
        ("done_dir", str),
        ("failed_dir", str),
        ("calculator_path", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, "
                f"got {type(config[key]).__name__}",
                action="main",
            )

    queue_config = config.get("queue")
    if not isinstance(queue_config, dict):
        raise SystemException("Missing required [queue] config section", action="main")

    for key in ("db_path", "lease_timeout", "max_retries"):
        if key not in queue_config:
            raise SystemException(f"Missing required [queue] config key: {key}", action="main")
    if type(queue_config["db_path"]) is not str or not queue_config["db_path"]:
        raise SystemException(
            "Config key 'queue.db_path' must be a non-empty string", action="main"
        )
    if type(queue_config["lease_timeout"]) is not int or queue_config["lease_timeout"] <= 0:
        raise SystemException(
            f"Config key 'queue.lease_timeout' must be a positive int, "
            f"got {queue_config['lease_timeout']!r}",
            action="main",
        )
    if type(queue_config["max_retries"]) is not int or queue_config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'queue.max_retries' must be a non-negative int, "
            f"got {queue_config['max_retries']!r}",
            action="main",
        )


def scan_inbox(config: dict, queue: SqliteQueue) -> int:
    """Add new CSV files in the input directory as queue items."""
    input_dir = Path(str(config["input_dir"]))
    if not input_dir.exists():
        raise SystemException(
            f"Input directory does not exist: {input_dir}", action="scan_inbox"
        )

    count = 0
    for csv_file in sorted(input_dir.glob("*.csv")):
        reference = f"calculator-{csv_file.stem}"
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
    """Build a 6-skill transaction for one CSV file.

    Note: transaction.state is seeded from item.payload by run_queue_loop()
    via _seed_transaction_state_from_payload() — no manual state= needed.
    """
    return Transaction(
        reference=item.reference,
        skills=[
            LoadExpressions(name="load_expressions", execution_order=1),
            OpenCalculator(name="open_calculator", execution_order=2),
            ProcessExpressions(name="process_expressions", execution_order=3),
            CloseCalculator(name="close_calculator", execution_order=4),
            WriteReport(name="write_report", execution_order=5),
            MoveFile(name="move_file", execution_order=6),
        ],
    )


def _move_failed_file(item: QueueItem, config: dict) -> None:
    """Move a failed CSV file to the failed directory."""
    file_path = item.payload.get("file_path")
    failed_dir = config.get("failed_dir")
    if not isinstance(file_path, str) or not isinstance(failed_dir, str):
        return

    src = Path(file_path)
    if not src.exists():
        return

    dst_dir = Path(failed_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = _unique_destination(dst_dir, src.name)

    try:
        shutil.move(str(src), str(dst))
    except OSError:
        logger.exception("Failed to move %s to %s", src, dst)


def _unique_destination(directory: Path, filename: str) -> Path:
    dst = directory / filename
    if not dst.exists():
        return dst

    stem = dst.stem
    suffix = dst.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate

    raise SystemException(f"Unable to find available destination for {filename}", action="move_file")


def _load_example_config() -> dict:
    config_path = Path(__file__).with_name("config.toml")
    config = dict(load_config(str(config_path)))
    base_dir = config_path.parent

    for key in ("input_dir", "output_dir", "done_dir", "failed_dir", "transaction_db_path"):
        value = config.get(key)
        if isinstance(value, str):
            path = Path(value)
            if not path.is_absolute():
                config[key] = str(base_dir / path)

    queue_config = config.get("queue")
    if isinstance(queue_config, dict):
        queue_config = dict(queue_config)
        db_path = queue_config.get("db_path")
        if isinstance(db_path, str):
            path = Path(db_path)
            if not path.is_absolute():
                queue_config["db_path"] = str(base_dir / path)
        config["queue"] = queue_config

    return config


def main() -> None:
    config = _load_example_config()
    _validate_config(config)

    allowed_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    if config["log_level"] not in allowed_levels:
        raise SystemException(f"Invalid log_level: {config['log_level']!r}", action="main")
    configure_logger(level=str(config["log_level"]))

    for key in ("input_dir", "done_dir", "failed_dir"):
        Path(str(config[key])).mkdir(parents=True, exist_ok=True)

    queue = SqliteQueue(config["queue"])
    enqueued = scan_inbox(config, queue)
    logger.info("Enqueued %d CSV file(s).", enqueued)

    engine = Engine(max_retries=int(config["engine_max_retries"]))

    def after_item(item: QueueItem, transaction: Transaction | None, error: Exception | None) -> None:
        if transaction is not None:
            if transaction.status is not Status.SUCCESSFUL:
                _move_failed_file(item, config)
        elif error is not None:
            _move_failed_file(item, config)

    class _NoopCredentials:
        """Minimal credential provider — no secrets needed for local CLI."""
        def get(self, name: str) -> str:
            return ""

    summary = run_queue_loop(
        queue,
        engine,
        build_transaction,
        config,
        credentials=_NoopCredentials(),
        worker_id="calculator-worker",
        logger=logger,
        after_item=after_item,
        transaction_db_path=str(config["transaction_db_path"]),
    )

    logger.info(
        "Queue run complete. processed=%d completed=%d failed=%d callback_errors=%d",
        summary.processed,
        summary.completed,
        summary.failed,
        summary.callback_errors,
    )
    if summary.failed > 0 or summary.callback_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
