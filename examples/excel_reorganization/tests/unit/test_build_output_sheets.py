from __future__ import annotations

import pytest
from openpyxl import load_workbook
from rpacore import BusinessException

from skills.build_output_sheets import BuildOutputSheets
from tests.conftest import make_context


def _grouped_data() -> dict:
    return {
        "2024-01": [
            {"employee_name": "Alice", "date": "2024-01-05", "amount": 10.0, "country": "USA"},
            {"employee_name": "Zoe", "date": "2024-01-10", "amount": 15.5, "country": "UK"},
        ],
        "2024-02": [
            {"employee_name": "Bob", "date": "2024-02-01", "amount": 7.0, "country": "Canada"},
        ],
    }


def test_build_output_sheets_creates_formatted_workbook(tmp_path):
    ctx = make_context(
        {
            "grouped_data": _grouped_data(),
            "output_dir": str(tmp_path),
            "output_filename": "sales_report_{month}.xlsx",
        }
    )

    BuildOutputSheets(name="build_output_sheets", execution_order=1).execute(ctx)

    output_path = tmp_path / "sales_report_2024-01.xlsx"
    assert ctx.data["output_path"] == str(output_path)

    workbook = load_workbook(output_path)
    assert workbook.sheetnames == ["2024-01", "2024-02"]
    ws = workbook["2024-01"]
    assert ws["A1"].font.bold is True
    assert ws["A1"].fill.fill_type == "solid"
    assert ws["A4"].value == "Subtotal"
    assert ws["C4"].value == 25.5
    assert workbook["2024-02"].max_row == 3
    assert workbook["2024-02"]["A3"].font.bold is True


def test_build_output_sheets_honors_literal_output_filename(tmp_path):
    ctx = make_context(
        {
            "grouped_data": _grouped_data(),
            "output_dir": str(tmp_path),
            "output_filename": "custom.xlsx",
        }
    )

    BuildOutputSheets(name="build_output_sheets", execution_order=1).execute(ctx)

    assert (tmp_path / "custom.xlsx").exists()
    assert ctx.data["output_path"] == str(tmp_path / "custom.xlsx")


def test_build_output_sheets_rejects_empty_grouped_data(tmp_path):
    ctx = make_context(
        {
            "grouped_data": {},
            "output_dir": str(tmp_path),
            "output_filename": "custom.xlsx",
        }
    )

    with pytest.raises(BusinessException, match="No grouped data"):
        BuildOutputSheets(name="build_output_sheets", execution_order=1).execute(ctx)
