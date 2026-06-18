"""Main orchestrator for Excel reorganization example.

This script loads sales data from CSV, groups by month, and outputs Excel files.
"""

from __future__ import annotations
import sys
from pathlib import Path
from rpacore import (
    Engine,
    ProcessContext,
    Status,
    Transaction,
    SystemException,
    load_config,
    save_transaction,
    get_logger,
    configure_logger,
)
from rpacore.paths import resolve_config_paths
from skills import (
    LoadSalesData,
    GroupByMonth,
    BuildOutputSheets,
    VerifyOutput,
)

logger = get_logger(__name__)

# The project root is the directory containing main.py.
# All config paths (csv_path, output_dir, transaction_db_path) must resolve
# under this root to prevent path traversal attacks.
PROJECT_ROOT = Path(__file__).resolve().parent

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def _validate_config(config: dict) -> None:
    """Validate config and resolve path values to absolute paths under PROJECT_ROOT.

    Mutates *config* in-place: relative paths are replaced with resolved
    absolute paths after safety checks pass.
    """
    if "transaction_db_path" not in config and "db_path" in config:
        raise SystemException(
            "Config key 'db_path' has been renamed to 'transaction_db_path'",
            action="validate_config",
        )

    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("csv_path", str),
        ("output_dir", str),
        ("transaction_db_path", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="validate_config")
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="validate_config",
            )

    # log_level validation
    if config["log_level"] not in LOG_LEVELS:
        raise SystemException(
            f"Config key 'log_level' must be one of {sorted(LOG_LEVELS)}, got {config['log_level']!r}",
            action="validate_config",
        )

    # Path-type keys: resolved safely under PROJECT_ROOT via resolve_config_paths
    resolve_config_paths(
        config,
        ["csv_path", "output_dir", "transaction_db_path"],
        base_dir=PROJECT_ROOT,
    )
    for key in ("csv_path", "output_dir", "transaction_db_path"):
        raw_path = Path(str(config[key]))
        resolved = (raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path).resolve()
        if not resolved.is_relative_to(PROJECT_ROOT):
            raise SystemException(
                f"Config key '{key}' must resolve under {PROJECT_ROOT}",
                action="validate_config",
            )
        config[key] = str(resolved)


def _cleanup_failed_output(tx: Transaction, logger) -> None:
    """Remove generated output when a later skill fails the transaction."""
    output_path = tx.state.get("output_path")
    if not isinstance(output_path, str):
        return

    try:
        Path(output_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Failed to clean output after workflow failure: %s", exc)


def main() -> None:
    """Run the Excel reorganization workflow."""
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))
    logger = get_logger(__name__)

    csv_path = config["csv_path"]
    output_dir = config["output_dir"]
    output_filename = config.get("output_filename", "sales_report_{month}.xlsx")

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Create transaction with all skills and seed initial state
    tx = Transaction(
        reference="excel-reorganization",
        state={
            "output_filename": output_filename,
        },
        metadata={
            "example": "excel_reorganization",
            "source_csv": csv_path,
        },
        skills=[
            LoadSalesData(name="load_sales_data", execution_order=1),
            GroupByMonth(name="group_by_month", execution_order=2),
            BuildOutputSheets(name="build_output_sheets", execution_order=3),
            VerifyOutput(name="verify_output", execution_order=4),
        ],
    )

    # Run transaction
    engine = Engine(max_retries=config["max_retries"])
    engine.run(ProcessContext(transaction=tx, config=config))

    if tx.status is not Status.SUCCESSFUL:
        failed = tx.failed_skills()
        details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
        logger.error("Workflow failed (%s). Failed skill(s): %s", tx.status, details)
        _cleanup_failed_output(tx, logger)
        sys.exit(1)

    try:
        save_transaction(tx, db_path=config["transaction_db_path"])
    except Exception as exc:
        _cleanup_failed_output(tx, logger)
        raise SystemException(f"Failed to persist transaction: {exc}", action="save_transaction") from exc

    logger.info("Excel reorganization completed successfully")


if __name__ == "__main__":
    main()
