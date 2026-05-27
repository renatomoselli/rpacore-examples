"""Main orchestrator for Excel reorganization example.

This script loads sales data from CSV, groups by month, and outputs Excel files.
"""

from __future__ import annotations
import sys
from pathlib import Path
from oref import (
    Engine,
    ProcessContext,
    Status,
    Transaction,
    BusinessException,
    SystemException,
    load_config,
    save_transaction,
    get_logger,
    configure_logger,
)
from skills import (
    LoadSalesData,
    GroupByMonth,
    BuildOutputSheets,
    VerifyOutput,
)

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    """Validate config has required keys and types."""
    required_keys = ["max_retries", "log_level", "csv_path", "output_dir"]
    missing_keys = set(required_keys) - set(config.keys())
    if missing_keys:
        raise SystemException(f"Config missing required keys: {missing_keys}", action="validate_config")

    expected_types = {
        "max_retries": int,
        "log_level": str,
        "csv_path": str,
        "output_dir": str,
    }
    for key, expected_type in expected_types.items():
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"{key} must be {expected_type.__name__}",
                action="validate_config",
            )

    if config["log_level"] not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        raise SystemException(f"Invalid log_level: {config['log_level']}", action="validate_config")

    # Note: db_path is not required for CSV→Excel workflow (no database involved)
    # It will be used only if future features add database persistence


def main() -> None:
    """Run the Excel reorganization workflow."""
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))
    logger = get_logger(__name__)

    csv_path = str(config["csv_path"])
    output_dir = str(config["output_dir"])

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Shared context for all skills
    shared_data: dict = {
        "sales_data": None,
        "grouped_data": None,
        "output_path": None,
        "expected_months": set(),
        "csv_path": str(config["csv_path"]),
        "output_dir": str(config["output_dir"]),
        "output_filename": str(config.get("output_filename", "sales_report_{month}.xlsx")),
    }

    # Create transaction with all skills
    tx = Transaction(
        reference="excel-reorganization",
        skills=[
            LoadSalesData(name="load_sales_data", execution_order=1),
            GroupByMonth(name="group_by_month", execution_order=2),
            BuildOutputSheets(name="build_output_sheets", execution_order=3),
            VerifyOutput(name="verify_output", execution_order=4),
        ],
    )

    # Run transaction
    engine = Engine(max_retries=int(config["max_retries"]))
    engine.run(ProcessContext(transaction=tx, config=config, data=shared_data))
    save_transaction(tx, db_path=config.get("db_path", "oref.db"))

    if tx.status is not Status.SUCCESSFUL:
        failed = tx.failed_skills()
        details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
        logger.error("Workflow failed (%s). Failed skill(s): %s", tx.status, details)
        sys.exit(1)

    logger.info("Excel reorganization completed successfully")


if __name__ == "__main__":
    main()
