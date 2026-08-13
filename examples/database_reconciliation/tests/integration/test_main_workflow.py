from __future__ import annotations

import pytest

from rpacore import list_transactions

import main as reconciliation_main
from steps.classify_outcome import ClassifyOutcome
from steps.match_transaction import MatchTransaction


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
        match="max_retries expected int; got bool",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_negative_max_retries(tmp_path):
    config = _valid_config(tmp_path)
    config["max_retries"] = -1

    with pytest.raises(
        reconciliation_main.SystemException,
        match="max_retries expected int >= 0",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_unknown_log_level(tmp_path):
    config = _valid_config(tmp_path)
    config["log_level"] = "TRACE"

    with pytest.raises(
        reconciliation_main.SystemException,
        match="log_level expected one of",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_returns_contained_paths_without_mutating_input(tmp_path, monkeypatch):
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": "state/rpacore.db",
        "internal_records_csv": "input/internal.csv",
        "bank_statement_csv": "input/bank.csv",
        "report_file": "output/report.csv",
        "extension_setting": "retained",
    }

    validated = reconciliation_main._validate_config(config)

    assert config["transaction_db_path"] == "state/rpacore.db"
    assert config["extension_setting"] == "retained"
    assert validated["transaction_db_path"] == str(tmp_path / "state" / "rpacore.db")
    assert validated["internal_records_csv"] == str(tmp_path / "input" / "internal.csv")
    assert validated["bank_statement_csv"] == str(tmp_path / "input" / "bank.csv")
    assert validated["report_file"] == str(tmp_path / "output" / "report.csv")
    assert validated["extension_setting"] == "retained"


def test_validate_config_rejects_empty_report_path(tmp_path):
    config = _valid_config(tmp_path)
    config["report_file"] = ""

    with pytest.raises(
        reconciliation_main.SystemException,
        match="report_file expected non-empty str",
    ):
        reconciliation_main._validate_config(config)


def test_validate_config_rejects_path_outside_project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
    config = _valid_config(tmp_path)
    config["report_file"] = str(tmp_path.parent / "outside.csv")

    with pytest.raises(reconciliation_main.SystemException) as exc_info:
        reconciliation_main._validate_config(config)

    assert str(exc_info.value).startswith("report_file resolves outside root")
    assert exc_info.value.action == "report_file"
    assert not str(exc_info.value).startswith("Invalid config:")
    assert exc_info.value.__cause__ is None


def test_validate_config_wraps_path_resolution_os_error(tmp_path, monkeypatch):
    sentinel = PermissionError("access denied")
    monkeypatch.setattr(
        reconciliation_main,
        "resolve_config_paths",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sentinel),
    )

    with pytest.raises(reconciliation_main.SystemException) as exc_info:
        reconciliation_main._validate_config(_valid_config(tmp_path))

    assert str(exc_info.value) == "Invalid config: access denied"
    assert exc_info.value.action == "main"
    assert exc_info.value.__cause__ is sentinel


def test_last_failure_message_uses_exception_text():
    tx = reconciliation_main.Transaction(
        reference="failed",
        steps=[ClassifyOutcome(name="classify_outcome", execution_order=1)],
    )
    tx.status = reconciliation_main.Status.FAILED
    tx.steps[0].status = reconciliation_main.Status.FAILED
    tx.steps[0].exceptions.append(RuntimeError("boom"))

    assert reconciliation_main._last_failure_message(tx) == "boom"


def test_last_failure_message_falls_back_to_status():
    tx = reconciliation_main.Transaction(reference="failed", steps=[])
    tx.status = reconciliation_main.Status.FAILED

    assert reconciliation_main._last_failure_message(tx) == "failed"


def test_missing_result_message_identifies_match_failure():
    tx = reconciliation_main.Transaction(
        reference="payment-PAY-1",
        steps=[
            MatchTransaction(name="match_transaction", execution_order=1),
            ClassifyOutcome(name="classify_outcome", execution_order=2),
        ],
    )
    tx.status = reconciliation_main.Status.FAILED
    tx.steps[0].status = reconciliation_main.Status.FAILED
    tx.steps[0].exceptions.append(RuntimeError("missing reference"))

    message = reconciliation_main._missing_result_message({"payment_id": "PAY-1"}, tx)

    assert message == (
        "Payment PAY-1 matching failed before classification could produce a "
        "reconciliation result: missing reference"
    )


def test_main_fails_before_report_when_payment_produces_no_result(tmp_path, monkeypatch):
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
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
        lambda _path, *, require_file: {
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


def test_main_reports_match_failure_before_classification(tmp_path, monkeypatch):
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
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
        lambda _path, *, require_file: {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        },
    )

    def fail_match(self, ctx):
        raise reconciliation_main.SystemException("missing reference", action=self.name)

    monkeypatch.setattr(MatchTransaction, "execute", fail_match)

    with pytest.raises(
        reconciliation_main.SystemException,
        match="matching failed before classification",
    ):
        reconciliation_main.main()

    assert not report_file.exists()


def test_main_exits_nonzero_after_writing_report_for_discrepancies(tmp_path, monkeypatch):
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
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
        lambda _path, *, require_file: {
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


def test_main_loads_required_config_from_project_root(tmp_path, monkeypatch):
    internal_csv = tmp_path / "internal.csv"
    bank_csv = tmp_path / "bank.csv"
    report_file = tmp_path / "output" / "report.csv"
    db_path = tmp_path / "rpacore.db"
    internal_csv.write_text(
        "payment_id,date,reference,amount,vendor\nPAY-1,2024-04-01,INV-1,100.00,Vendor A\n",
        encoding="utf-8",
    )
    bank_csv.write_text(
        "posted_date,reference,amount,description\n2024-04-01,INV-1,100.00,ACH Vendor A\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation_main, "PROJECT_ROOT", tmp_path)
    observed = {}

    def load_project_config(path, *, require_file):
        observed["path"] = path
        observed["require_file"] = require_file
        return {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": str(db_path),
            "internal_records_csv": str(internal_csv),
            "bank_statement_csv": str(bank_csv),
            "report_file": str(report_file),
        }

    monkeypatch.setattr(reconciliation_main, "load_config", load_project_config)

    reconciliation_main.main()

    assert observed == {
        "path": tmp_path / "config.toml",
        "require_file": True,
    }
    assert report_file.exists()
