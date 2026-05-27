"""Verify output Excel file is readable and complete.

This skill verifies that the output Excel file can be read with openpyxl,
contains all expected months, and has the correct structure (header + data + subtotal).

Pattern: Follows examples/json_event_log_processor/skills/validate_events.py:3-64
"""

from __future__ import annotations
from pathlib import Path
from openpyxl import load_workbook
from oref import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class VerifyOutput(Skill):
    """Verify output Excel file is readable and complete."""

    def execute(self, ctx: ProcessContext) -> None:
        """Verify output file exists, is readable, and has correct structure."""
        output_path = ctx.data.get("output_path")
        expected_months = ctx.data.get("expected_months")
        grouped_data = ctx.data.get("grouped_data")

        if output_path is None:
            raise BusinessException("No output_path in context.", action=self.name)
        if expected_months is None:
            raise BusinessException("No expected_months in context.", action=self.name)
        if grouped_data is None:
            raise BusinessException("No grouped_data in context.", action=self.name)

        output_path = Path(output_path)

        # Check file exists
        if not output_path.exists():
            raise SystemException(f"Output file does not exist: {output_path}", action=self.name)

        # Verify file is readable
        try:
            workbook = load_workbook(output_path)
        except Exception as exc:
            raise SystemException(f"Cannot read output file: {exc}", action=self.name) from exc

        # Verify sheet names match expected months
        actual_months = list(workbook.sheetnames)
        missing_months = set(expected_months) - set(actual_months)
        extra_months = set(actual_months) - set(expected_months)

        if missing_months:
            raise SystemException(
                f"Missing months in output: {missing_months}",
                action=self.name,
            )
        if extra_months:
            raise SystemException(
                f"Unexpected months in output: {extra_months}",
                action=self.name,
            )

        for month in expected_months:
            ws = workbook[month]
            rows = list(ws.iter_rows(values_only=True))
            month_data = grouped_data.get(month, [])

            expected_rows = len(month_data) + 2
            if len(rows) != expected_rows:
                raise SystemException(
                    f"Sheet '{month}' has {len(rows)} rows; expected {expected_rows}",
                    action=self.name,
                )

            if tuple(rows[0]) != ("Employee Name", "Date", "Amount", "Country"):
                raise SystemException(
                    f"Sheet '{month}' has incorrect header: {rows[0]}",
                    action=self.name,
                )

            # Verify subtotal row exists
            if rows[-1][0] != "Subtotal":
                raise SystemException(
                    f"Sheet '{month}' missing subtotal row",
                    action=self.name,
                )

            data_rows = rows[1:-1]
            expected_names = [row["employee_name"] for row in month_data]
            actual_names = [row[0] for row in data_rows]
            if actual_names != expected_names:
                raise SystemException(
                    f"Sheet '{month}' has incorrect employee ordering",
                    action=self.name,
                )

            expected_subtotal = sum(float(row["amount"]) for row in month_data)
            actual_subtotal = rows[-1][2]
            if actual_subtotal != expected_subtotal:
                raise SystemException(
                    f"Sheet '{month}' subtotal {actual_subtotal} does not match expected {expected_subtotal}",
                    action=self.name,
                )

        logger.info("Output verification passed: %s", output_path)
