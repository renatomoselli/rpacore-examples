from __future__ import annotations

from oref import Engine, ProcessContext, Status, Transaction

from skills.validate_schema import ValidateSchema


def _run(rows):
    tx = Transaction(
        reference="validate-report",
        skills=[ValidateSchema(name="validate_schema", execution_order=1)],
    )
    data = {"report_rows": rows}
    Engine(max_retries=0).run(ProcessContext(transaction=tx, data=data))
    return tx, data


def test_validate_schema_accepts_valid_report():
    tx, data = _run(
        [
            {
                "branch_id": "101",
                "date": "2024-03-01",
                "revenue": "12450.75",
                "headcount": "23",
            }
        ]
    )

    assert tx.status == Status.SUCCESSFUL
    assert data["validated_report"]["branch_id"] == 101
    assert data["validated_report"]["date"] == "2024-03-01"
    assert data["validation_failed"] is False


def test_validate_schema_rejects_zero_headcount():
    tx, data = _run(
        [
            {
                "branch_id": "101",
                "date": "2024-03-01",
                "revenue": "12450.75",
                "headcount": "0",
            }
        ]
    )

    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True
    failed = tx.failed_skills()[0]
    assert "headcount must be greater than zero" in str(failed.exceptions[-1])


def test_rejects_empty_rows():
    tx, data = _run([])
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True


def test_rejects_multiple_rows():
    row = {
        "branch_id": "101",
        "date": "2024-03-01",
        "revenue": "100.00",
        "headcount": "5",
    }
    tx, data = _run([row, row])
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True
    assert "exactly one data row" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_rejects_negative_revenue():
    tx, data = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "-10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True
    assert "revenue" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_rejects_non_positive_branch_id():
    tx, data = _run(
        [{"branch_id": "0", "date": "2024-01-01", "revenue": "10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True
    assert "branch_id" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_rejects_missing_required_column():
    tx, data = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "10"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True
    assert "headcount" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_rejects_empty_string_column():
    tx, data = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True


def test_rejects_invalid_date_format():
    tx, data = _run(
        [{"branch_id": "1", "date": "01-03-2024", "revenue": "10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True


def test_rejects_non_numeric_revenue():
    tx, data = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "abc", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert data["validation_failed"] is True


def test_raises_when_no_rows():
    tx, data = _run(None)
    assert tx.status == Status.FAILED
    assert "No report rows" in str(tx.failed_skills()[0].exceptions[-1])
