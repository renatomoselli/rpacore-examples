from __future__ import annotations

from pathlib import Path

from rpacore import (
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

# The project root is the directory containing main.py.
# All config paths (inbox_dir, results_dir, db_path) must resolve
# under this root to prevent path traversal attacks.  [S1, S2]
PROJECT_ROOT = Path(__file__).resolve().parent

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
MAX_RETRIES_UPPER_BOUND = 10  # Upper bound for max_retries config


def _validate_config(config: dict) -> None:
    """Validate config and resolve path values to absolute paths under PROJECT_ROOT.

    Mutates *config* in-place: relative paths are replaced with resolved
    absolute paths after safety checks pass.
    """
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("inbox_dir", str),
        ("results_dir", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        # Use ``type() is`` instead of isinstance() to reject bool subclasses
        # of int/str (e.g. ``max_retries = True`` must not pass as int).  [Q2, Q18]
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )

    # max_retries bounds  [Q3]
    max_retries = config["max_retries"]
    if max_retries < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {max_retries}",
            action="main",
        )
    if max_retries > MAX_RETRIES_UPPER_BOUND:
        raise SystemException(
            f"Config key 'max_retries' must be <= {MAX_RETRIES_UPPER_BOUND}, got {max_retries}",
            action="main",
        )

    # log_level validation  [Q3]
    if config["log_level"] not in LOG_LEVELS:
        raise SystemException(
            f"Config key 'log_level' must be one of {sorted(LOG_LEVELS)}, got {config['log_level']!r}",
            action="main",
        )

    # Path-type keys: non-empty strings, resolved safely under PROJECT_ROOT  [S1, S2]
    for dir_key in ("inbox_dir", "results_dir"):
        dir_path = config[dir_key]
        if not isinstance(dir_path, str) or not dir_path:
            raise SystemException(
                f"Config key '{dir_key}' must be a non-empty string",
                action="main",
            )
        resolved = (PROJECT_ROOT / dir_path).resolve()
        if not resolved.is_relative_to(PROJECT_ROOT):
            raise SystemException(
                f"Config key '{dir_key}' resolves outside project root: {resolved}",
                action="main",
            )
        config[dir_key] = str(resolved)

    # db_path: also ensure it resolves under PROJECT_ROOT  [S1, S2]
    db_path = config["db_path"]
    resolved_db = (PROJECT_ROOT / db_path).resolve()
    if not resolved_db.is_relative_to(PROJECT_ROOT):
        raise SystemException(
            f"Config key 'db_path' resolves outside project root: {resolved_db}",
            action="main",
        )
    config["db_path"] = str(resolved_db)


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=config["max_retries"])
    db_path = config["db_path"]
    inbox_dir = config["inbox_dir"]
    results_dir = config["results_dir"]

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

    # Verify every globbed file resolves under inbox_dir  [S2]
    for jf in json_files:
        if not jf.resolve().is_relative_to(inbox_path.resolve()):
            raise SystemException(
                f"Inbox file escapes inbox directory: {jf}",
                action="main",
            )

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
        engine.run(ProcessContext(transaction=error_tx, config=config, data={}))
        save_transaction(error_tx, db_path=db_path)
        logger.info("No files to process. Exiting.")
        return

    # --- One transaction per file ---
    successful = 0
    failed = 0

    for json_file in json_files:
        # Fresh shared_data per file — avoids stale state leaking across
        # transactions (Q1, precedent: rest_api_batch commit 4bdd1de).
        shared_data: dict = {
            "current_file": str(json_file),
            "results_dir": results_dir,
        }

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
    engine.run(ProcessContext(transaction=error_tx, config=config, data={}))
    save_transaction(error_tx, db_path=db_path)

    logger.info(
        "Batch complete. %d successful, %d failed out of %d files.",
        successful, failed, len(json_files),
    )

if __name__ == "__main__":
    main()
