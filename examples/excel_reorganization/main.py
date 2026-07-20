"""Main orchestrator for Excel reorganization example.

This script loads sales data from CSV, groups by month, and outputs Excel files.
"""

from __future__ import annotations
import sys
from pathlib import Path
from rpacore import (
    ConfigField,
    Engine,
    Status,
    Transaction,
    SystemException,
    execute_transaction,
    load_config,
    get_logger,
    configure_logger,
    validate_config,
)
from rpacore import resolve_config_paths
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

CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, choices=LOG_LEVELS),
    ConfigField("csv_path", str, allow_empty=False),
    ConfigField("output_dir", str, allow_empty=False),
    ConfigField("transaction_db_path", str, allow_empty=False),
)


def _validate_config(config: dict[str, object]) -> dict[str, object]:
    """Return validated config with paths contained under ``PROJECT_ROOT``."""
    if "db_path" in config:
        raise SystemException(
            "Config key 'db_path' has been renamed to 'transaction_db_path'",
            action="validate_config",
        )

    try:
        validated = validate_config(config, CONFIG_FIELDS)
        resolved = resolve_config_paths(
            validated,
            ["csv_path", "output_dir", "transaction_db_path"],
            base_dir=PROJECT_ROOT,
            root=PROJECT_ROOT,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="validate_config") from exc

    csv_path = Path(str(resolved["csv_path"]))
    if not csv_path.is_file():
        raise SystemException(
            f"Config key 'csv_path' must name an existing file: {csv_path}",
            action="validate_config",
        )
    if "output_filename" in config:
        resolved["output_filename"] = config["output_filename"]
    return resolved


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
    config = _validate_config(load_config(PROJECT_ROOT / "config.toml", require_file=True))
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

    try:
        execute_transaction(
            tx,
            config=config,
            engine=Engine(max_retries=int(config["max_retries"])),
            transaction_db_path=str(config["transaction_db_path"]),
        )
    except Exception as exc:
        _cleanup_failed_output(tx, logger)
        raise SystemException(
            f"Failed to execute and checkpoint transaction: {exc}",
            action="execute_transaction",
        ) from exc

    if tx.status is not Status.SUCCESSFUL:
        failed = tx.failed_skills()
        details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
        logger.error("Workflow failed (%s). Failed skill(s): %s", tx.status, details)
        _cleanup_failed_output(tx, logger)
        sys.exit(1)

    logger.info("Excel reorganization completed successfully")


if __name__ == "__main__":
    main()
