from __future__ import annotations

import pytest

from oref import SystemException, Transaction

import main as reconciliation_main
from skills.match_transaction import MatchTransaction


def test_main_fails_before_report_when_payment_produces_no_result(tmp_path, monkeypatch):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "oref.db"

    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01,INV-1,100.00,Vendor A",
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reconciliation_main,
        "load_config",
        lambda _path: {
            "max_retries": 0,
            "log_level": "WARNING",
            "db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        },
    )

    def build_transaction_without_classifier(payment):
        return Transaction(
            reference=f"payment-{payment.get('payment_id')}",
            skills=[MatchTransaction(name="match_transaction", execution_order=1)],
        )

    monkeypatch.setattr(
        reconciliation_main,
        "build_payment_transaction",
        build_transaction_without_classifier,
    )

    with pytest.raises(SystemException, match="did not produce a reconciliation result"):
        reconciliation_main.main()

    assert not report_file.exists()


def test_main_exits_nonzero_after_writing_report_for_discrepancies(tmp_path, monkeypatch):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "oref.db"

    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01,INV-1,100.00,Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01,INV-1,125.00,ACH Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reconciliation_main,
        "load_config",
        lambda _path: {
            "max_retries": 0,
            "log_level": "WARNING",
            "db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        reconciliation_main.main()

    assert exc_info.value.code == 1
    assert report_file.exists()
