from __future__ import annotations

import pytest
from openpyxl import Workbook
from rpacore import SystemException

from skills.verify_output import VerifyOutput
from tests.conftest import make_context


def _grouped_data() -> dict:
    return {
        "2024-01": [
            {"employee_name": "Alice", "date": "2024-01-05", "amount": 10.0, "country": "USA"},
            {"employee_name": "Zoe", "date": "2024-01-10", "amount": 15.5, "country": "UK"},
        ]
    }


def _write_workbook(path, rows):
    workbook = Workbook()
    ws = workbook.active
    ws.title = "2024-01"
    for row in rows:
        ws.append(row)
    workbook.save(path)


def test_verify_output_accepts_complete_workbook(tmp_path):
    output_path = tmp_path / "sales.xlsx"
    _write_workbook(
        output_path,
        [
            ["Employee Name", "Date", "Amount", "Country"],
            ["Alice", "2024-01-05", 10.0, "USA"],
            ["Zoe", "2024-01-10", 15.5, "UK"],
            ["Subtotal", "", 25.5, ""],
        ],
    )
    ctx = make_context(
        state={
            "output_path": str(output_path),
            "expected_months": ["2024-01"],
            "grouped_data": _grouped_data(),
        },
    )
    # Seed transaction metadata (normally set by BuildOutputSheets)
    ctx.transaction.metadata.update({
        "source_csv": "sample.csv",
        "row_count": 2,
        "month_count": 1,
        "output_path": str(output_path),
        "employee_count": 2,
        "generated_at": "2024-01-15T00:00:00+00:00",
    })

    VerifyOutput(name="verify_output", execution_order=1).execute(ctx)


def test_verify_output_rejects_missing_data_rows(tmp_path):
    output_path = tmp_path / "sales.xlsx"
    _write_workbook(
        output_path,
        [
            ["Employee Name", "Date", "Amount", "Country"],
            ["Subtotal", "", 25.5, ""],
        ],
    )
    ctx = make_context(
        state={
            "output_path": str(output_path),
            "expected_months": ["2024-01"],
            "grouped_data": _grouped_data(),
        },
    )
    ctx.transaction.metadata.update({
        "source_csv": "sample.csv",
        "row_count": 2,
        "month_count": 1,
        "output_path": str(output_path),
        "employee_count": 2,
        "generated_at": "2024-01-15T00:00:00+00:00",
    })

    with pytest.raises(SystemException, match="expected 4"):
        VerifyOutput(name="verify_output", execution_order=1).execute(ctx)


def test_verify_output_rejects_wrong_subtotal(tmp_path):
    output_path = tmp_path / "sales.xlsx"
    _write_workbook(
        output_path,
        [
            ["Employee Name", "Date", "Amount", "Country"],
            ["Alice", "2024-01-05", 10.0, "USA"],
            ["Zoe", "2024-01-10", 15.5, "UK"],
            ["Subtotal", "", 99.0, ""],
        ],
    )
    ctx = make_context(
        state={
            "output_path": str(output_path),
            "expected_months": ["2024-01"],
            "grouped_data": _grouped_data(),
        },
    )
    ctx.transaction.metadata.update({
        "source_csv": "sample.csv",
        "row_count": 2,
        "month_count": 1,
        "output_path": str(output_path),
        "employee_count": 2,
        "generated_at": "2024-01-15T00:00:00+00:00",
    })

    with pytest.raises(SystemException, match="subtotal"):
        VerifyOutput(name="verify_output", execution_order=1).execute(ctx)


def test_verify_output_rejects_missing_metadata(tmp_path):
    output_path = tmp_path / "sales.xlsx"
    _write_workbook(
        output_path,
        [
            ["Employee Name", "Date", "Amount", "Country"],
            ["Alice", "2024-01-05", 10.0, "USA"],
            ["Subtotal", "", 10.0, ""],
        ],
    )
    ctx = make_context(
        state={
            "output_path": str(output_path),
            "expected_months": ["2024-01"],
            "grouped_data": {"2024-01": [{"employee_name": "Alice", "date": "2024-01-05", "amount": 10.0, "country": "USA"}]},
        },
    )
    # Do NOT seed metadata — should fail

    with pytest.raises(SystemException, match="Transaction.metadata missing"):
        VerifyOutput(name="verify_output", execution_order=1).execute(ctx)
