from __future__ import annotations

import csv

from rpacore import Engine, ProcessContext, Status, Transaction

from steps.write_reconciliation_report import WriteReconciliationReport


def _run(config, state):
    tx = Transaction(
        reference="write-reconciliation-report",
        state=state,
        steps=[WriteReconciliationReport(name="write_reconciliation_report", execution_order=1)],
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
    assert tx.artifacts[0].metadata["status_counts"] == {
        "matched": 1,
        "missing_from_bank": 0,
        "amount_mismatch": 0,
        "type_error": 0,
    }

    with report_file.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["payment_id"] == "PAY-1"
    assert rows[0]["internal_amount"] == "100.00"
    assert rows[0]["status"] == "matched"


def test_write_reconciliation_report_counts_type_errors_without_changing_rows(tmp_path):
    report_file = tmp_path / "report.csv"
    results = [
        {"payment_id": "PAY-1", "status": "matched", "reason_code": ""},
        {"payment_id": "PAY-2", "status": "amount_mismatch", "reason_code": "amount_mismatch"},
        {"payment_id": "PAY-3", "status": "type_error", "reason_code": "type_error"},
        {"payment_id": "PAY-4", "status": "type_error", "reason_code": "type_error"},
    ]

    tx = _run(
        {"report_file": str(report_file)},
        {"reconciliation_results": results},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.artifacts[0].metadata == {
        "record_count": 4,
        "status_counts": {
            "matched": 1,
            "missing_from_bank": 0,
            "amount_mismatch": 1,
            "type_error": 2,
        },
    }

    with report_file.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[2]["status"] == "type_error"
    assert rows[2]["reason_code"] == "type_error"


def test_write_reconciliation_report_fails_without_results(tmp_path):
    report_file = tmp_path / "report.csv"

    tx = _run({"report_file": str(report_file)}, {})

    assert tx.status == Status.FAILED
    assert "reconciliation_results" in str(tx.failed_steps()[0].exceptions[-1])
    assert not report_file.exists()


def test_write_reconciliation_report_preserves_destination_on_write_failure(tmp_path, monkeypatch):
    report_file = tmp_path / "report.csv"
    report_file.write_text("previous report\n", encoding="utf-8")

    def fail_writerow(self, rowdict):
        raise OSError("disk full")

    monkeypatch.setattr(csv.DictWriter, "writerow", fail_writerow)

    tx = _run(
        {"report_file": str(report_file)},
        {"reconciliation_results": [{"payment_id": "PAY-1"}]},
    )

    assert tx.status == Status.FAILED
    assert report_file.read_text(encoding="utf-8") == "previous report\n"
    assert list(tmp_path.glob(".report.csv.*.tmp")) == []
