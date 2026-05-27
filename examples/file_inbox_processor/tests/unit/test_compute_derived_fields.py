from __future__ import annotations

from decimal import Decimal

from oref import Engine, ProcessContext, Status, Transaction

from skills.compute_derived_fields import ComputeDerivedFields


def test_compute_derived_fields_adds_revenue_per_headcount():
    tx = Transaction(
        reference="compute-report",
        skills=[ComputeDerivedFields(name="compute_derived_fields", execution_order=1)],
    )
    data = {
        "validated_report": {
            "branch_id": 101,
            "date": "2024-03-01",
            "revenue": Decimal("12450.75"),
            "headcount": 23,
        }
    }

    Engine(max_retries=0).run(ProcessContext(transaction=tx, data=data))

    assert tx.status == Status.SUCCESSFUL
    assert data["processed_report"]["revenue_per_headcount"] == Decimal("541.34")
