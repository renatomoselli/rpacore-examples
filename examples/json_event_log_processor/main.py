from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from rpacore import (
    ConfigField,
    Engine,
    ProcessContext,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    save_transaction,
    validate_config,
)

from skills.load_json_file import LoadJsonFile
from skills.validate_events import ValidateEvents
from skills.normalize_events import NormalizeEvents
from skills.write_output import WriteOutput
from skills.write_error_report import WriteErrorReport

logger = get_logger(__name__)
FILE_DEFINITION_IDENTITY = "json-event-log-processor/file/v1"
ERROR_REPORT_DEFINITION_IDENTITY = "json-event-log-processor/error-report/v1"

# The project root is the directory containing main.py.
# All config paths (inbox_dir, results_dir, transaction_db_path) must resolve
# under this root to prevent path traversal attacks.  [S1, S2]
PROJECT_ROOT = Path(__file__).resolve().parent

LOG_LEVELS = ("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING")
MAX_RETRIES_UPPER_BOUND = 10  # Upper bound for max_retries config
PATH_KEYS = ("transaction_db_path", "inbox_dir", "results_dir")
CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0, max_value=MAX_RETRIES_UPPER_BOUND),
    ConfigField("log_level", str, choices=LOG_LEVELS),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("inbox_dir", str, allow_empty=False),
    ConfigField("results_dir", str, allow_empty=False),
)


def _record_persistence_error(config: dict[str, Any], tx: Transaction, exc: Exception) -> None:
    errors = config.setdefault("persistence_errors", [])
    if isinstance(errors, list):
        errors.append({
            "transaction_reference": tx.reference,
            "transaction_id": tx.id,
            "status": tx.status.name,
            "exception_type": exc.__class__.__name__,
            "message": str(exc),
        })


def _save_transaction_safely(tx: Transaction, db_path: str, config: dict[str, Any]) -> bool:
    try:
        save_transaction(tx, db_path=db_path)
    except Exception as exc:
        _record_persistence_error(config, tx, exc)
        logger.exception(
            "Failed to persist transaction %s; continuing batch",
            tx.reference,
        )
        return False
    return True


def _make_error_report_tx(run_id: str, report_attempt: int = 1) -> Transaction:
    return Transaction(
        reference="error-report",
        definition_identity=ERROR_REPORT_DEFINITION_IDENTITY,
        state={"run_id": run_id},
        metadata={
            "example": "json_event_log_processor",
            "run_id": run_id,
            "transaction_kind": "error-report",
            "report_attempt": report_attempt,
        },
        skills=[
            WriteErrorReport(name="write_error_report", execution_order=1),
        ],
    )


def _run_error_report(engine: Engine, config: dict[str, Any], db_path: str, run_id: str) -> None:
    error_tx = _make_error_report_tx(run_id, report_attempt=1)
    engine.run(ProcessContext(transaction=error_tx, config=config))
    if _save_transaction_safely(error_tx, db_path, config):
        return

    logger.warning("Refreshing error report after error-report transaction persistence failed")
    refreshed_error_tx = _make_error_report_tx(run_id, report_attempt=2)
    engine.run(ProcessContext(transaction=refreshed_error_tx, config=config))


def _validate_config(config: dict[str, object]) -> dict[str, object]:
    """Return validated config with paths contained under ``PROJECT_ROOT``."""
    if "db_path" in config:
        raise SystemException(
            "Config key 'db_path' has been renamed to 'transaction_db_path'",
            action="main",
        )

    try:
        validated = validate_config(config, CONFIG_FIELDS)
        return resolve_config_paths(
            {**config, **validated},
            PATH_KEYS,
            base_dir=PROJECT_ROOT,
            root=PROJECT_ROOT,
        )
    except SystemException:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc


def main() -> None:
    config = _validate_config(load_config(PROJECT_ROOT / "config.toml", require_file=True))
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=config["max_retries"])
    db_path = config["transaction_db_path"]
    inbox_dir = config["inbox_dir"]
    results_dir = config["results_dir"]
    run_id = f"json-event-log-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    config["run_id"] = run_id

    # Ensure results directory exists
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # --- List files in inbox (setup) ---
    inbox_path = Path(inbox_dir)
    if not inbox_path.exists():
        raise SystemException(
            f"Inbox directory does not exist: {inbox_dir}",
            action="main",
        )

    json_files = sorted(inbox_path.glob("*.json"))

    logger.info("Found %d JSON files in %s", len(json_files), inbox_dir)

    if not json_files:
        logger.warning("No JSON files found in %s. Nothing to process.", inbox_dir)
        # Still run error report (will be empty)
        _run_error_report(engine, config, db_path, run_id)
        logger.info("No files to process. Exiting.")
        return

    # --- One transaction per file ---
    successful = 0
    persisted_successful = 0
    failed = 0
    unresolved = 0

    for json_file in json_files:
        file_tx = Transaction(
            reference=f"json-file-{json_file.stem}",
            definition_identity=FILE_DEFINITION_IDENTITY,
            state={"current_file": str(json_file)},
            metadata={
                "example": "json_event_log_processor",
                "run_id": run_id,
                "source_file": json_file.name,
            },
            skills=[
                LoadJsonFile(name="load_json_file", execution_order=1),
                ValidateEvents(name="validate_events", execution_order=2),
                NormalizeEvents(name="normalize_events", execution_order=3),
                WriteOutput(name="write_output", execution_order=4),
            ],
        )
        engine.run(ProcessContext(transaction=file_tx, config=config))
        events = file_tx.state.get("events")
        if isinstance(events, list):
            file_tx.metadata["event_count"] = len(events)
        failed_skills = file_tx.failed_skills()
        file_tx.metadata["error_count"] = sum(
            len(skill.exceptions) for skill in failed_skills
        )
        persisted = _save_transaction_safely(file_tx, db_path, config)

        if file_tx.status == Status.SUCCESSFUL:
            successful += 1
            if persisted:
                persisted_successful += 1
                logger.info("Processed: %s", json_file.name)
            else:
                logger.warning("Processed but could not persist: %s", json_file.name)
        elif file_tx.status == Status.FAILED:
            failed += 1
            if failed_skills:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed_skills)
                logger.warning("File %s failed: %s", json_file.name, details)
            else:
                logger.warning("File %s: %s", json_file.name, file_tx.status)
        else:
            unresolved += 1
            logger.warning("File %s unresolved: %s", json_file.name, file_tx.status)

    # --- Error report transaction ---
    _run_error_report(engine, config, db_path, run_id)

    logger.info(
        "Batch complete. %d successful (%d persisted), %d failed, %d unresolved out of %d files.",
        successful, persisted_successful, failed, unresolved, len(json_files),
    )

if __name__ == "__main__":
    main()
