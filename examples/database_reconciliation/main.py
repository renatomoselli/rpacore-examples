from __future__ import annotations

import sys

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

from skills.classify_outcome import ClassifyOutcome
from skills.load_bank_statement import LoadBankStatement
from skills.load_internal_records import LoadInternalRecords
from skills.match_transaction import MatchTransaction
from skills.write_reconciliation_report import WriteReconciliationReport

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("internal_records_csv", str),
        ("bank_statement_csv", str),
        ("report_file", str),
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


def build_payment_transaction(payment: dict[str, object]) -> Transaction:
    return Transaction(
        reference=f"payment-{payment.get('payment_id')}",
        skills=[
            MatchTransaction(name="match_transaction", execution_order=1),
            ClassifyOutcome(name="classify_outcome", execution_order=2),
        ],
    )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["db_path"])
    shared_data: dict = {"reconciliation_results": []}

    setup_tx = Transaction(
        reference="load-reconciliation-inputs",
        skills=[
            LoadInternalRecords(name="load_internal_records", execution_order=1),
            LoadBankStatement(name="load_bank_statement", execution_order=2),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config, data=shared_data))
    save_transaction(setup_tx, db_path=db_path)

    if setup_tx.status != Status.SUCCESSFUL:
        logger.error("Setup failed (%s). Aborting.", setup_tx.status)
        sys.exit(1)

    if "internal_records" not in shared_data:
        raise SystemException("Setup did not produce internal_records", action="main")
    internal_records = shared_data["internal_records"]
    if not isinstance(internal_records, list):
        raise SystemException("Setup produced invalid internal_records", action="main")
    logger.info("Loaded %d internal payment record(s).", len(internal_records))

    matched = 0
    discrepancies = 0
    for payment in internal_records:
        shared_data["current_payment"] = payment
        shared_data.pop("bank_candidates", None)
        shared_data.pop("reconciliation_result", None)

        payment_tx = build_payment_transaction(payment)
        engine.run(ProcessContext(transaction=payment_tx, config=config, data=shared_data))
        save_transaction(payment_tx, db_path=db_path)

        result = shared_data.get("reconciliation_result")
        if isinstance(result, dict):
            shared_data["reconciliation_results"].append(result)
        else:
            failed = payment_tx.failed_skills()
            details = failed[-1].exceptions[-1] if failed and failed[-1].exceptions else str(payment_tx.status)
            raise SystemException(
                f"Payment {payment.get('payment_id')} did not produce a reconciliation result: {details}",
                action="main",
            )

        if payment_tx.status == Status.SUCCESSFUL:
            matched += 1
        else:
            discrepancies += 1
            failed = payment_tx.failed_skills()
            if failed:
                logger.warning(
                    "Payment %s discrepancy: %s",
                    payment.get("payment_id"),
                    failed[-1].exceptions[-1],
                )

    report_tx = Transaction(
        reference="write-reconciliation-report",
        skills=[
            WriteReconciliationReport(name="write_reconciliation_report", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=report_tx, config=config, data=shared_data))
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
