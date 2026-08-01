from __future__ import annotations

import sys
from pathlib import Path
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

from skills.classify_outcome import ClassifyOutcome
from skills.load_bank_statement import LoadBankStatement
from skills.load_internal_records import LoadInternalRecords
from skills.match_transaction import MatchTransaction
from skills.write_reconciliation_report import WriteReconciliationReport

logger = get_logger(__name__)
SETUP_DEFINITION_IDENTITY = "database-reconciliation/setup/v1"
PAYMENT_DEFINITION_IDENTITY = "database-reconciliation/payment/v1"
REPORT_DEFINITION_IDENTITY = "database-reconciliation/report/v1"


# The project root is the directory containing main.py.
# All config paths must resolve under this root to prevent path traversal.
PROJECT_ROOT = Path(__file__).resolve().parent

LOG_LEVELS = ("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING")
PATH_KEYS = (
    "transaction_db_path",
    "internal_records_csv",
    "bank_statement_csv",
    "report_file",
)
CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, choices=LOG_LEVELS),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("internal_records_csv", str, allow_empty=False),
    ConfigField("bank_statement_csv", str, allow_empty=False),
    ConfigField("report_file", str, allow_empty=False),
)


def _last_failure_message(tx: Transaction) -> str:
    failed = tx.failed_skills()
    if not failed:
        return str(tx.status)
    exceptions = getattr(failed[-1], "exceptions", [])
    if not exceptions:
        return str(tx.status)
    return str(exceptions[-1])


def _missing_result_message(payment: dict, payment_tx: Transaction) -> str:
    details = _last_failure_message(payment_tx)
    failed_skill_names = {skill.name for skill in payment_tx.failed_skills()}
    payment_id = payment.get("payment_id")

    if "match_transaction" in failed_skill_names:
        return (
            f"Payment {payment_id} matching failed before classification could "
            f"produce a reconciliation result: {details}"
        )
    if "classify_outcome" in failed_skill_names:
        return (
            f"Payment {payment_id} classification failed without producing a "
            f"reconciliation result: {details}"
        )
    return f"Payment {payment_id} did not produce a reconciliation result: {details}"


def _validate_config(config: dict[str, object]) -> dict[str, object]:
    """Return validated config with paths contained under ``PROJECT_ROOT``."""
    if "db_path" in config:
        raise SystemException(
            "Config key 'db_path' has been renamed to 'transaction_db_path'",
            action="main",
        )

    try:
        validated = validate_config(config, CONFIG_FIELDS)
        resolved = resolve_config_paths(
            {**config, **validated},
            PATH_KEYS,
            base_dir=PROJECT_ROOT,
            root=PROJECT_ROOT,
        )
    except SystemException:
        raise
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc

    return resolved


def main() -> None:
    config = _validate_config(load_config(PROJECT_ROOT / "config.toml", require_file=True))
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["transaction_db_path"])
    run_id = str(uuid4())

    # --- Setup transaction: load internal records and bank statement ---
    setup_tx = Transaction(
        reference="load-reconciliation-inputs",
        definition_identity=SETUP_DEFINITION_IDENTITY,
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
            definition_identity=PAYMENT_DEFINITION_IDENTITY,
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
            raise SystemException(
                _missing_result_message(payment, payment_tx),
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
        definition_identity=REPORT_DEFINITION_IDENTITY,
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
