from __future__ import annotations

import csv
from pathlib import Path

from rpacore import Engine, ProcessContext, Status, Transaction, save_transaction

from skills.classify_outcome import ClassifyOutcome
from skills.load_bank_statement import LoadBankStatement
from skills.load_internal_records import LoadInternalRecords
from skills.match_transaction import MatchTransaction
from skills.write_reconciliation_report import WriteReconciliationReport


def test_full_workflow_writes_reconciliation_report(tmp_path):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "rpacore.db"

    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01,INV-1,100.00,Vendor A",
                "PAY-2,2024-04-01,INV-2,200.00,Vendor B",
                "PAY-3,2024-04-02,INV-3,300.00,Vendor C",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01,INV-1,100.00,ACH Vendor A",
                "2024-04-01,INV-2,250.00,ACH Vendor B",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(db_path),
        "internal_records_csv": str(internal_csv),
        "bank_statement_csv": str(bank_csv),
        "report_file": str(report_file),
    }
    engine = Engine(max_retries=0)

    setup_tx = Transaction(
        reference="load-reconciliation-inputs",
        state={},
        skills=[
            LoadInternalRecords(name="load_internal_records", execution_order=1),
            LoadBankStatement(name="load_bank_statement", execution_order=2),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config))
    save_transaction(setup_tx, db_path=str(db_path))

    assert setup_tx.status == Status.SUCCESSFUL

    internal_records = setup_tx.state["internal_records"]
    bank_by_reference = setup_tx.state["bank_by_reference"]

    reconciliation_results = []
    statuses = []
    for payment in internal_records:
        payment_tx = Transaction(
            reference=f"payment-{payment.get('payment_id')}",
            state={
                "current_payment": payment,
                "bank_by_reference": bank_by_reference,
            },
            skills=[
                MatchTransaction(name="match_transaction", execution_order=1),
                ClassifyOutcome(name="classify_outcome", execution_order=2),
            ],
        )
        engine.run(ProcessContext(transaction=payment_tx, config=config))
        save_transaction(payment_tx, db_path=str(db_path))
        statuses.append(payment_tx.status)
        result = payment_tx.state.get("reconciliation_result")
        if isinstance(result, dict):
            reconciliation_results.append(result)

    report_tx = Transaction(
        reference="write-reconciliation-report",
        state={"reconciliation_results": reconciliation_results},
        skills=[
            WriteReconciliationReport(name="write_reconciliation_report", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=report_tx, config=config))
    save_transaction(report_tx, db_path=str(db_path))

    assert statuses == [Status.SUCCESSFUL, Status.FAILED, Status.FAILED]
    assert report_tx.status == Status.SUCCESSFUL
    assert report_file.exists()

    with report_file.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["status"] for row in rows] == [
        "matched",
        "amount_mismatch",
        "missing_from_bank",
    ]
    assert rows[1]["reason_code"] == "amount_mismatch"
    assert rows[2]["reason_code"] == "missing_from_bank"
