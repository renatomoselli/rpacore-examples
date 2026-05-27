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
