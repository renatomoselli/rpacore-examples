from __future__ import annotations

import pytest
from oref import BusinessException

from skills.group_by_month import GroupByMonth
from tests.conftest import make_context


def test_group_by_month_groups_and_sorts_by_employee():
    ctx = make_context(
        {
            "sales_data": [
                {"employee_name": "Zoe", "date": "2024-01-10", "amount": 3.0, "country": "USA"},
                {"employee_name": "Alice", "date": "2024-01-05", "amount": 1.0, "country": "USA"},
                {"employee_name": "Bob", "date": "2024-02-01", "amount": 2.0, "country": "UK"},
            ]
        }
    )

    GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)

    assert set(ctx.data["grouped_data"]) == {"2024-01", "2024-02"}
    assert [row["employee_name"] for row in ctx.data["grouped_data"]["2024-01"]] == ["Alice", "Zoe"]
    assert ctx.data["expected_months"] == {"2024-01", "2024-02"}


def test_group_by_month_requires_sales_data():
    ctx = make_context({})

    with pytest.raises(BusinessException, match="No sales_data"):
        GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)
