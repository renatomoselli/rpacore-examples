from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from rpacore import (
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
)

from skills.classify_outcome import ClassifyOutcome
from skills.load_bank_statement import LoadBankStatement
from skills.load_internal_records import LoadInternalRecords
from skills.match_transaction import MatchTransaction
from skills.write_reconciliation_report import WriteReconciliationReport

logger = get_logger(__name__)


# The project root is the directory containing main.py.
# All config paths must resolve under this root to prevent path traversal.
PROJECT_ROOT = Path(__file__).resolve().parent

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _last_failure_message(tx: Transaction) -> str:
    failed = tx.failed_skills()
    if not failed:
        return str(tx.status)
    exceptions = getattr(failed[-1], "exceptions", [])
    if not exceptions:
        return str(tx.status)
    return str(exceptions[-1])


def _validate_config(config: dict) -> None:
    """Validate config and resolve path values to absolute paths under PROJECT_ROOT."""
    if "transaction_db_path" not in config and "db_path" in config:
        raise SystemException(
            "Config key 'db_path' has been renamed to 'transaction_db_path'",
            action="main",
        )

    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
        ("internal_records_csv", str),
        ("bank_statement_csv", str),
        ("report_file", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        # Use exact type checks so booleans do not pass as integers.
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )
    if config["log_level"] not in LOG_LEVELS:
        raise SystemException(
            f"Config key 'log_level' must be one of {sorted(LOG_LEVELS)}, got {config['log_level']!r}",
            action="main",
        )

    # Resolve paths safely under PROJECT_ROOT (relative paths only)
    path_keys = ["transaction_db_path", "internal_records_csv", "bank_statement_csv", "report_file"]
    relative_path_keys = [
        key for key in path_keys if not Path(str(config[key])).is_absolute()
    ]
    if relative_path_keys:
        resolved = resolve_config_paths(
            config,
            relative_path_keys,
            base_dir=PROJECT_ROOT,
            root=PROJECT_ROOT,
        )
        config.update(resolved)


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["transaction_db_path"])
    run_id = str(uuid4())

    # --- Setup transaction: load internal records and bank statement ---
    setup_tx = Transaction(
        reference="load-reconciliation-inputs",
        state={},
        metadata={
            "example": "database_reconciliation",
            "run_id": run_id,
            "transaction_type": "setup",
        },
        skills=[
            LoadInternalRecords(name="load_internal_records", execution_order=1),
            LoadBankStatement(name="load_bank_statement", execution_order=2),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config))

    if setup_tx.status != Status.SUCCESSFUL:
        save_transaction(setup_tx, db_path=db_path)
        logger.error("Setup failed (%s). Aborting.", setup_tx.status)
        sys.exit(1)

    internal_records = setup_tx.state.get("internal_records")
    if not isinstance(internal_records, list):
        raise SystemException("Setup did not produce internal_records", action="main")
    logger.info("Loaded %d internal payment record(s).", len(internal_records))

    bank_by_reference = setup_tx.state.get("bank_by_reference")
    if not isinstance(bank_by_reference, dict):
        raise SystemException("Setup did not produce bank_by_reference", action="main")

    # Enrich setup transaction metadata
    setup_tx.metadata["record_count"] = len(internal_records)
    setup_tx.metadata["bank_entry_count"] = sum(
        len(entries) for entries in bank_by_reference.values()
    )
    save_transaction(setup_tx, db_path=db_path)

    # --- Per-payment reconciliation loop ---
    reconciliation_results: list[dict[str, object]] = []
    matched = 0
    discrepancies = 0

    for payment in internal_records:
        payment_tx = Transaction(
            reference=f"payment-{payment.get('payment_id')}",
            state={
                "current_payment": payment,
                "bank_by_reference": bank_by_reference,
            },
            metadata={
                "example": "database_reconciliation",
                "run_id": run_id,
                "transaction_type": "payment",
                "payment_id": payment.get("payment_id"),
                "reference": payment.get("reference"),
            },
            skills=[
                MatchTransaction(name="match_transaction", execution_order=1),
                ClassifyOutcome(name="classify_outcome", execution_order=2),
            ],
        )
        engine.run(ProcessContext(transaction=payment_tx, config=config))

        result = payment_tx.state.get("reconciliation_result")
        if isinstance(result, dict):
            reconciliation_results.append(result)
        else:
            details = _last_failure_message(payment_tx)
            raise SystemException(
                f"Payment {payment.get('payment_id')} did not produce a reconciliation result: {details}",
                action="main",
            )

        # Enrich payment transaction metadata
        payment_tx.metadata["reconciliation_status"] = result["status"]
        save_transaction(payment_tx, db_path=db_path)

        if payment_tx.status == Status.SUCCESSFUL:
            matched += 1
        else:
            discrepancies += 1
            logger.warning(
                "Payment %s discrepancy: %s",
                payment.get("payment_id"),
                _last_failure_message(payment_tx),
            )

    # --- Report transaction ---
    report_tx = Transaction(
        reference="write-reconciliation-report",
        state={"reconciliation_results": reconciliation_results},
        metadata={
            "example": "database_reconciliation",
            "run_id": run_id,
            "transaction_type": "report",
        },
        skills=[
            WriteReconciliationReport(name="write_reconciliation_report", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=report_tx, config=config))
    save_transaction(report_tx, db_path=db_path)

    logger.info(
        "Reconciliation complete. matched=%d discrepancies=%d report=%s",
        matched,
        discrepancies,
        config["report_file"],
    )
    if discrepancies > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
