"""Unit tests for ValidateSchema step."""

from __future__ import annotations

import pytest

from rpacore import Engine, ProcessContext, Status, SystemException, Transaction

from steps.validate_schema import ValidateSchema


def _run(rows):
    tx = Transaction(
        reference="validate-report",
        steps=[ValidateSchema(name="validate_schema", execution_order=1)],
    )
    # Seed state with report_rows (the input to this step)
    tx.state["report_rows"] = rows
    Engine(max_retries=0).run(ProcessContext(transaction=tx))
    return tx


def test_validate_schema_accepts_valid_report():
    tx = _run(
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
    assert tx.state["validated_report"]["branch_id"] == 101
    assert tx.state["validated_report"]["date"] == "2024-03-01"
    # revenue is serialized to str() for JSON safety
    assert tx.state["validated_report"]["revenue"] == "12450.75"
    assert tx.state["validated_report"]["headcount"] == 23


def test_validate_schema_rejects_zero_headcount():
    tx = _run(
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
    assert tx.state["validation_failed"] is True
    failed = tx.failed_steps()[0]
    assert "headcount must be greater than zero" in str(failed.exceptions[-1])


def test_rejects_empty_rows():
    tx = _run([])
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "got 0 rows" in str(tx.failed_steps()[0].exceptions[-1])


def test_non_list_rows_is_system_error():
    tx = _run({"branch_id": "101"})
    assert tx.status == Status.FAILED
    assert "validation_failed" not in tx.state
    failed = tx.failed_steps()[0]
    assert isinstance(failed.exceptions[-1], SystemException)
    assert "Expected report_rows to be a list" in str(failed.exceptions[-1])


def test_rejects_multiple_rows():
    row = {
        "branch_id": "101",
        "date": "2024-03-01",
        "revenue": "100.00",
        "headcount": "5",
    }
    tx = _run([row, row])
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "exactly one data row" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_negative_revenue():
    tx = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "-10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "revenue" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_non_positive_branch_id():
    tx = _run(
        [{"branch_id": "0", "date": "2024-01-01", "revenue": "10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "branch_id" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_missing_required_column():
    tx = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "10"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "headcount" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_empty_string_column():
    tx = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "revenue" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_invalid_date_format():
    tx = _run(
        [{"branch_id": "1", "date": "01-03-2024", "revenue": "10", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "invalid" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_rejects_non_numeric_revenue():
    tx = _run(
        [{"branch_id": "1", "date": "2024-01-01", "revenue": "abc", "headcount": "1"}]
    )
    assert tx.status == Status.FAILED
    assert tx.state["validation_failed"] is True
    assert "invalid" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_raises_when_no_rows():
    tx = _run(None)
    assert tx.status == Status.FAILED
    assert "No report rows" in str(tx.failed_steps()[0].exceptions[-1])
