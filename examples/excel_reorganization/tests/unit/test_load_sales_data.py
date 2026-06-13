from __future__ import annotations

import pytest
from rpacore import BusinessException, SystemException

from skills.load_sales_data import LoadSalesData
from tests.conftest import make_context


def test_load_sales_data_valid_csv(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "employee_name,date,amount,country\n"
        "Alice,2024-01-15,10.50,USA\n",
        encoding="utf-8",
    )
    ctx = make_context(config={"csv_path": str(csv_path)})

    LoadSalesData(name="load_sales_data", execution_order=1).execute(ctx)

    assert ctx.state["sales_data"] == [
        {
            "employee_name": "Alice",
            "date": "2024-01-15",
            "amount": 10.5,
            "country": "USA",
        }
    ]


def test_load_sales_data_missing_column(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("employee_name,date,amount\nAlice,2024-01-15,10.50\n", encoding="utf-8")
    ctx = make_context(config={"csv_path": str(csv_path)})

    with pytest.raises(SystemException, match="missing required columns"):
        LoadSalesData(name="load_sales_data", execution_order=1).execute(ctx)


def test_load_sales_data_invalid_date(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "employee_name,date,amount,country\nAlice,01/15/2024,10.50,USA\n",
        encoding="utf-8",
    )
    ctx = make_context(config={"csv_path": str(csv_path)})

    with pytest.raises(BusinessException, match="invalid date format"):
        LoadSalesData(name="load_sales_data", execution_order=1).execute(ctx)
