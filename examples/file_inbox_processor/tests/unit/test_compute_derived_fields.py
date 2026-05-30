from __future__ import annotations

from decimal import Decimal

from oref import Engine, ProcessContext, Status, Transaction

from skills.compute_derived_fields import ComputeDerivedFields


def _run(data):
    tx = Transaction(
        reference="compute-report",
        skills=[ComputeDerivedFields(name="compute_derived_fields", execution_order=1)],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=tx, data=data))
    return tx, data


def test_compute_derived_fields_adds_revenue_per_headcount():
    tx, data = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": Decimal("12450.75"),
                "headcount": 23,
            }
        }
    )

    assert tx.status == Status.SUCCESSFUL
    assert data["processed_report"]["revenue_per_headcount"] == Decimal("541.34")


def test_skips_when_validation_failed():
    tx, data = _run(
        {
            "validation_failed": True,
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": Decimal("100.00"),
                "headcount": 1,
            },
        }
    )
    assert tx.status == Status.SUCCESSFUL
    assert "processed_report" not in data


def test_zero_headcount_raises():
    tx, _ = _run(
        {
            "validated_report": {
                "branch_id": 101,
                "date": "2024-03-01",
                "revenue": Decimal("100.00"),
                "headcount": 0,
            }
        }
    )
    assert tx.status == Status.FAILED
    assert "headcount" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_missing_validated_report_raises():
    tx, _ = _run({})
    assert tx.status == Status.FAILED
    assert "No validated report" in str(tx.failed_skills()[0].exceptions[-1])


def test_zero_revenue_yields_zero_per_headcount():
    tx, data = _run(
        {
            "validated_report": {
                "branch_id": 200,
                "date": "2024-06-15",
                "revenue": Decimal("0.00"),
                "headcount": 10,
            }
        }
    )
    assert tx.status == Status.SUCCESSFUL
    assert data["processed_report"]["revenue_per_headcount"] == Decimal("0.00")
