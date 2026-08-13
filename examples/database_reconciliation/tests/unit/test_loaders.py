from __future__ import annotations

from rpacore import Engine, ProcessContext, Status, Transaction

from steps.load_bank_statement import LoadBankStatement
from steps.load_internal_records import LoadInternalRecords


def _run_step(step, config):
    tx = Transaction(
        reference="load",
        state={},
        steps=[step],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config))
    return tx


def test_load_internal_records_rejects_missing_headers(tmp_path):
    internal_csv = tmp_path / "internal.csv"
    internal_csv.write_text("foo,bar\n", encoding="utf-8")

    tx = _run_step(
        LoadInternalRecords(name="load_internal_records", execution_order=1),
        {"internal_records_csv": str(internal_csv)},
    )

    assert tx.status == Status.FAILED
    assert "missing required header(s)" in str(tx.failed_steps()[0].exceptions[-1])
    assert "internal_records" not in tx.state


def test_load_internal_records_parses_valid_rows(tmp_path):
    internal_csv = tmp_path / "internal.csv"
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

    tx = _run_step(
        LoadInternalRecords(name="load_internal_records", execution_order=1),
        {"internal_records_csv": str(internal_csv)},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.state["internal_records"][0]["amount"] == "100.00"


def test_load_internal_records_strips_reference_whitespace(tmp_path):
    internal_csv = tmp_path / "internal.csv"
    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01, INV-1 ,100.00,Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadInternalRecords(name="load_internal_records", execution_order=1),
        {"internal_records_csv": str(internal_csv)},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.state["internal_records"][0]["reference"] == "INV-1"


def test_load_internal_records_rejects_invalid_amount(tmp_path):
    internal_csv = tmp_path / "internal.csv"
    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01,INV-1,not-a-number,Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadInternalRecords(name="load_internal_records", execution_order=1),
        {"internal_records_csv": str(internal_csv)},
    )

    assert tx.status == Status.FAILED
    assert "invalid amount" in str(tx.failed_steps()[0].exceptions[-1])


def test_load_internal_records_rejects_whitespace_required_values(tmp_path):
    internal_csv = tmp_path / "internal.csv"
    internal_csv.write_text(
        "\n".join(
            [
                "payment_id,date,reference,amount,vendor",
                "PAY-1,2024-04-01,   ,100.00,Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadInternalRecords(name="load_internal_records", execution_order=1),
        {"internal_records_csv": str(internal_csv)},
    )

    assert tx.status == Status.FAILED
    assert "missing required column(s): reference" in str(
        tx.failed_steps()[0].exceptions[-1]
    )


def test_load_bank_statement_rejects_missing_headers(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text("foo,bar\n", encoding="utf-8")

    tx = _run_step(
        LoadBankStatement(name="load_bank_statement", execution_order=1),
        {"bank_statement_csv": str(bank_csv)},
    )

    assert tx.status == Status.FAILED
    assert "missing required header(s)" in str(tx.failed_steps()[0].exceptions[-1])
    assert "bank_by_reference" not in tx.state


def test_load_bank_statement_indexes_entries_by_reference(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01,INV-1,100.00,ACH Vendor A",
                "2024-04-02,INV-1,125.00,ACH Vendor A followup",
            ]
        )
        + "\n",
    )

    tx = _run_step(
        LoadBankStatement(name="load_bank_statement", execution_order=1),
        {"bank_statement_csv": str(bank_csv)},
    )

    assert tx.status == Status.SUCCESSFUL
    assert len(tx.state["bank_by_reference"]["INV-1"]) == 2
    assert [entry["amount"] for entry in tx.state["bank_by_reference"]["INV-1"]] == [
        "100.00",
        "125.00",
    ]


def test_load_bank_statement_strips_reference_whitespace_for_index(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01, INV-1 ,100.00,ACH Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadBankStatement(name="load_bank_statement", execution_order=1),
        {"bank_statement_csv": str(bank_csv)},
    )

    assert tx.status == Status.SUCCESSFUL
    assert list(tx.state["bank_by_reference"]) == ["INV-1"]
    assert tx.state["bank_by_reference"]["INV-1"][0]["reference"] == "INV-1"


def test_load_bank_statement_rejects_invalid_amount(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01,INV-1,not-a-number,ACH Vendor A",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadBankStatement(name="load_bank_statement", execution_order=1),
        {"bank_statement_csv": str(bank_csv)},
    )

    assert tx.status == Status.FAILED
    assert "invalid amount" in str(tx.failed_steps()[0].exceptions[-1])


def test_load_bank_statement_rejects_whitespace_required_values(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "\n".join(
            [
                "posted_date,reference,amount,description",
                "2024-04-01,INV-1,100.00,   ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tx = _run_step(
        LoadBankStatement(name="load_bank_statement", execution_order=1),
        {"bank_statement_csv": str(bank_csv)},
    )

    assert tx.status == Status.FAILED
    assert "missing required column(s): description" in str(
        tx.failed_steps()[0].exceptions[-1]
    )
