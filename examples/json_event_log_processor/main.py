from __future__ import annotations

from pathlib import Path

from oref import (
    Engine,
    ProcessContext,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    save_transaction,
)

from skills.load_json_file import LoadJsonFile
from skills.validate_events import ValidateEvents
from skills.normalize_events import NormalizeEvents
from skills.write_output import WriteOutput
from skills.write_error_report import WriteErrorReport

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("inbox_dir", str),
        ("results_dir", str),
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
    for dir_key in ("inbox_dir", "results_dir"):
        dir_path = config[dir_key]
        if not isinstance(dir_path, str) or not dir_path:
            raise SystemException(
                f"Config key '{dir_key}' must be a non-empty string",
                action="main",
            )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["db_path"])
    inbox_dir = str(config["inbox_dir"])
    results_dir = str(config["results_dir"])
    shared_data: dict = {}

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
        error_tx = Transaction(
            reference="error-report",
            skills=[
                WriteErrorReport(name="write_error_report", execution_order=1),
            ],
        )
        engine.run(ProcessContext(transaction=error_tx, config=config, data=shared_data))
        save_transaction(error_tx, db_path=db_path)
        logger.info("No files to process. Exiting.")
        return

    # --- One transaction per file ---
    successful = 0
    failed = 0

    for json_file in json_files:
        shared_data["current_file"] = str(json_file)
        shared_data["results_dir"] = results_dir

        # Clear stale shared state from previous transaction
        shared_data.pop("events", None)
        shared_data.pop("normalized_events", None)
        shared_data.pop("validation_failed", None)

        file_tx = Transaction(
            reference=f"json-file-{json_file.stem}",
            skills=[
                LoadJsonFile(name="load_json_file", execution_order=1),
                ValidateEvents(name="validate_events", execution_order=2),
                NormalizeEvents(name="normalize_events", execution_order=3),
                WriteOutput(name="write_output", execution_order=4),
            ],
        )
        engine.run(ProcessContext(transaction=file_tx, config=config, data=shared_data))
        save_transaction(file_tx, db_path=db_path)

        if file_tx.status == Status.SUCCESSFUL:
            successful += 1
            logger.info("Processed: %s", json_file.name)
        else:
            failed += 1
            failed_skills = file_tx.failed_skills()
            if failed_skills:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed_skills)
                logger.warning("File %s failed: %s", json_file.name, details)
            else:
                logger.warning("File %s: %s", json_file.name, file_tx.status)

    # --- Error report transaction ---
    error_tx = Transaction(
        reference="error-report",
        skills=[
            WriteErrorReport(name="write_error_report", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=error_tx, config=config, data=shared_data))
    save_transaction(error_tx, db_path=db_path)

    logger.info(
        "Batch complete. %d successful, %d failed out of %d files.",
        successful, failed, len(json_files),
    )


if __name__ == "__main__":
    main()
