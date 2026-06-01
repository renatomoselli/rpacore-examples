"""Group sales data by year-month and sort by employee name.

This skill groups rows from ctx.data["sales_data"] by year-month key (YYYY-MM),
sorts each group by employee name, and stores the grouped data in
ctx.data["grouped_data"] as a dict[str, list[dict]].

Pattern: Follows examples/rpa_challenge/skills/validate_events.py:3-64
"""

from __future__ import annotations
from typing import Any
from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class GroupByMonth(Skill):
    """Group sales data by year-month and sort by employee name."""

    def execute(self, ctx: ProcessContext) -> None:
        """Group sales data by year-month, sort by employee name, and store in context."""
        sales_data = ctx.data.get("sales_data")
        if sales_data is None:
            raise BusinessException(
                "No sales_data in context — LoadSalesData must run before this skill",
                action=self.name,
            )

        # Group by year-month key (YYYY-MM)
        grouped_data: dict[str, list[dict[str, Any]]] = {}
        for row in sales_data:
            date_str = row.get("date")
            if not date_str:
                raise BusinessException("Row missing date field.", action=self.name)

            # Extract YYYY-MM from date string (format: YYYY-MM-DD)
            year_month = date_str[:7]

            if year_month not in grouped_data:
                grouped_data[year_month] = []
            grouped_data[year_month].append(row)

        # Sort each group by employee name (alphabetically)
        for year_month in grouped_data:
            grouped_data[year_month].sort(
                key=lambda x: x.get("employee_name", "").lower()
            )

        # Log completion
        logger.info("Grouped %d rows into %d months", len(sales_data), len(grouped_data))

        # Store in context
        ctx.data["grouped_data"] = grouped_data
        # Set expected months for VerifyOutput skill
        ctx.data["expected_months"] = set(grouped_data.keys())
        logger.info("Grouped %d rows into %d months", len(sales_data), len(grouped_data))
