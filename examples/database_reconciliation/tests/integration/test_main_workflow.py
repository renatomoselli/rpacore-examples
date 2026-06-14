from __future__ import annotations

import pytest

from rpacore import list_transactions

import main as reconciliation_main
from skills.classify_outcome import ClassifyOutcome


def _valid_config(tmp_path):
    return {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "internal_records_csv": str(tmp_path / "internal.csv"),
        "bank_statement_csv": str(tmp_path / "bank.csv"),
        "report_file": str(tmp_path / "report.csv"),
    }


def test_validate_config_rejects_legacy_db_path(tmp_path):
    config = _valid_config(tmp_path)
    config["db_path"] = config.pop("transaction_db_path")

    with pytest.raises(
        reconciliation_main.SystemException,
        match="renamed to 'transaction_db_path'",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_bool_max_retries(tmp_path):
    config = _valid_config(tmp_path)
    config["max_retries"] = True

    with pytest.raises(
        reconciliation_main.SystemException,
        match="must be int, got bool",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_negative_max_retries(tmp_path):
    config = _valid_config(tmp_path)
    config["max_retries"] = -1

    with pytest.raises(
        reconciliation_main.SystemException,
        match="must be >= 0",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_unknown_log_level(tmp_path):
    config = _valid_config(tmp_path)
    config["log_level"] = "TRACE"

    with pytest.raises(
        reconciliation_main.SystemException,
        match="must be one of",
    ):
        reconciliation_main._validate_config(config)


def test_main_fails_before_report_when_payment_produces_no_result(tmp_path, monkeypatch):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "rpacore.db"

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
            "transaction_db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        },
    )

    monkeypatch.setattr(ClassifyOutcome, "execute", lambda self, ctx: None)

    with pytest.raises(
        reconciliation_main.SystemException,
        match="did not produce a reconciliation result",
    ):
        reconciliation_main.main()

    assert not report_file.exists()


def test_main_exits_nonzero_after_writing_report_for_discrepancies(tmp_path, monkeypatch):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "rpacore.db"

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
            "transaction_db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        reconciliation_main.main()

    assert exc_info.value.code == 1
    assert report_file.exists()

    transactions_by_reference = {
        tx.reference: tx for tx in list_transactions(db_path=str(db_path), limit=10)
    }
    assert transactions_by_reference["load-reconciliation-inputs"].metadata[
        "record_count"
    ] == 1
    assert transactions_by_reference["load-reconciliation-inputs"].metadata[
        "bank_entry_count"
    ] == 1
    assert transactions_by_reference["payment-PAY-1"].metadata[
        "reconciliation_status"
    ] == "amount_mismatch"
