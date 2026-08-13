"""Unit tests for ComputeDerivedFields step."""

from __future__ import annotations

import pytest

from rpacore import Engine, ProcessContext, Status, Transaction

from steps.compute_derived_fields import ComputeDerivedFields


def _run(data):
    tx = Transaction(
        reference="compute-report",
        steps=[ComputeDerivedFields(name="compute_derived_fields", execution_order=1)],
    )
    # Seed state with validated_report (the input to this step)
    for key, value in data.items():
        tx.state[key] = value
    Engine(max_retries=0).run(ProcessContext(transaction=tx))
    return tx


def test_compute_derived_fields_adds_revenue_per_headcount():
    # revenue is str() from Slice 3 (ValidateSchema)
    tx = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": "12450.75",
                "headcount": 23,
            }
        }
    )

    assert tx.status == Status.SUCCESSFUL
    # revenue_per_headcount is str() for JSON safety
    assert tx.state["processed_report"]["revenue_per_headcount"] == "541.34"


def test_zero_headcount_raises():
    tx = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": "100.00",
                "headcount": 0,
            }
        }
    )
    assert tx.status == Status.FAILED
    assert "headcount" in str(tx.failed_steps()[0].exceptions[-1]).lower()


def test_missing_validated_report_raises():
    tx = _run({})
    assert tx.status == Status.FAILED
    assert "validated_report" in str(tx.failed_steps()[0].exceptions[-1])


def test_wrong_validated_report_types_have_specific_error():
    tx = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": 100,
                "headcount": "5",
            }
        }
    )
    assert tx.status == Status.FAILED
    message = str(tx.failed_steps()[0].exceptions[-1])
    assert "revenue must be str" in message
    assert "headcount must be int" in message


def test_invalid_decimal_revenue_has_specific_error():
    tx = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": "not-a-decimal",
                "headcount": 5,
            }
        }
    )
    assert tx.status == Status.FAILED
    message = str(tx.failed_steps()[0].exceptions[-1])
    assert "invalid revenue value" in message
    assert "unexpected types" not in message


def test_zero_revenue_yields_zero_per_headcount():
    tx = _run(
        {
            "validated_report": {
                "branch_id": 200,
                "date": "2024-06-15",
                "revenue": "0.00",
                "headcount": 10,
            }
        }
    )
    assert tx.status == Status.SUCCESSFUL
    assert tx.state["processed_report"]["revenue_per_headcount"] == "0.00"
