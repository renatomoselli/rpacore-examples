"""Group sales data by year-month and sort by employee name.

This skill groups rows from ctx.state["sales_data"] by year-month key (YYYY-MM),
sorts each group by employee name, and stores the grouped data in
ctx.state["grouped_data"] as a dict[str, list[dict]].

Pattern: Follows examples/json_event_log_processor/skills/load_json_file.py:52
"""

from __future__ import annotations
import datetime
from typing import Any
from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class GroupByMonth(Skill):
    """Group sales data by year-month and sort by employee name."""

    def execute(self, ctx: ProcessContext) -> None:
        """Group sales data by year-month, sort by employee name, and store in context."""
        sales_data = ctx.require_state("sales_data", list, action=self.name)

        # Group by year-month key (YYYY-MM)
        grouped_data: dict[str, list[dict[str, Any]]] = {}
        for i, row in enumerate(sales_data):
            date_str = row.get("date")
            if not date_str:
                raise BusinessException(f"Row {i + 1} missing date field", action=self.name, stop=True)
            try:
                datetime.datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError as exc:
                raise BusinessException(
                    f"Row {i + 1} has invalid date format: {date_str!r} (expected YYYY-MM-DD)",
                    action=self.name,
                    stop=True,
                ) from exc

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
        ctx.state["grouped_data"] = grouped_data
        # Set expected months for VerifyOutput skill. Keep durable state JSON-safe.
        ctx.state["expected_months"] = sorted(grouped_data.keys())
        # Keep expected subtotals independent from the workbook writer so VerifyOutput
        # can detect subtotal drift in the generated file.
        ctx.state["expected_subtotals"] = {
            year_month: sum(float(row["amount"]) for row in month_data)
            for year_month, month_data in grouped_data.items()
        }
