from __future__ import annotations

import pytest
from rpacore import BusinessException, SystemException

from skills.group_by_month import GroupByMonth
from tests.conftest import make_context


def test_group_by_month_groups_and_sorts_by_employee():
    ctx = make_context(
        state={
            "sales_data": [
                {"employee_name": "Zoe", "date": "2024-01-10", "amount": 3.0, "country": "USA"},
                {"employee_name": "Alice", "date": "2024-01-05", "amount": 1.0, "country": "USA"},
                {"employee_name": "Bob", "date": "2024-02-01", "amount": 2.0, "country": "UK"},
            ]
        }
    )

    GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)

    assert set(ctx.state["grouped_data"]) == {"2024-01", "2024-02"}
    assert [row["employee_name"] for row in ctx.state["grouped_data"]["2024-01"]] == ["Alice", "Zoe"]
    assert ctx.state["expected_months"] == ["2024-01", "2024-02"]
    assert ctx.state["expected_subtotals"] == {"2024-01": 4.0, "2024-02": 2.0}


def test_group_by_month_requires_sales_data():
    ctx = make_context()

    with pytest.raises(SystemException, match="Missing required state key: sales_data"):
        GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)


def test_group_by_month_missing_date_stops_downstream_skills():
    ctx = make_context(
        state={
            "sales_data": [
                {"employee_name": "Alice", "amount": 1.0, "country": "USA"},
            ]
        }
    )

    with pytest.raises(BusinessException, match="Row 1 missing date") as exc_info:
        GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)

    assert exc_info.value.stops_execution is True


def test_group_by_month_revalidates_date_format_when_state_is_seeded_directly():
    ctx = make_context(
        state={
            "sales_data": [
                {"employee_name": "Alice", "date": "bad", "amount": 1.0, "country": "USA"},
            ]
        }
    )

    with pytest.raises(BusinessException, match="Row 1 has invalid date format") as exc_info:
        GroupByMonth(name="group_by_month", execution_order=1).execute(ctx)

    assert exc_info.value.stops_execution is True
