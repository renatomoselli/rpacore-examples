from __future__ import annotations

import csv

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.write_reconciliation_report import WriteReconciliationReport


def _run(config, state):
    tx = Transaction(
        reference="write-reconciliation-report",
        state=state,
        skills=[WriteReconciliationReport(name="write_reconciliation_report", execution_order=1)],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config))
    return tx


def test_write_reconciliation_report_creates_parent_directory_and_rows(tmp_path):
    report_file = tmp_path / "nested" / "report.csv"

    tx = _run(
        {"report_file": str(report_file)},
        {
            "reconciliation_results": [
                {
                    "payment_id": "PAY-1",
                    "date": "2024-04-01",
                    "reference": "INV-1",
                    "vendor": "Vendor A",
                    "internal_amount": "100.00",
                    "bank_amount": "100.00",
                    "bank_date": "2024-04-01",
                    "status": "matched",
                    "reason_code": "",
                }
            ]
        },
    )

    assert tx.status == Status.SUCCESSFUL
    assert len(tx.artifacts) == 1
    assert tx.artifacts[0].name == "reconciliation_report"

    with report_file.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["payment_id"] == "PAY-1"
    assert rows[0]["internal_amount"] == "100.00"
    assert rows[0]["status"] == "matched"


def test_write_reconciliation_report_fails_without_results(tmp_path):
    report_file = tmp_path / "report.csv"

    tx = _run({"report_file": str(report_file)}, {})

    assert tx.status == Status.FAILED
    assert "reconciliation_results" in str(tx.failed_skills()[0].exceptions[-1])
    assert not report_file.exists()
