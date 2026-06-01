from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from rpacore import BusinessException, ProcessContext, Skill, SystemException

REQUIRED_COLUMNS = ("branch_id", "date", "revenue", "headcount")


class ValidateSchema(Skill):
    """Validate report schema and business rules."""

    def execute(self, ctx: ProcessContext) -> None:
        rows = ctx.data.get("report_rows")
        if rows is None:
            raise SystemException("No report rows in context", action=self.name)
        if not isinstance(rows, list) or not rows:
            ctx.data["validation_failed"] = True
            raise BusinessException("Report must contain exactly one data row", action=self.name)
        if len(rows) != 1:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                f"Report must contain exactly one data row, got {len(rows)}",
                action=self.name,
            )

        row = rows[0]
        missing = [column for column in REQUIRED_COLUMNS if column not in row or row[column] == ""]
        if missing:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                f"Report missing required column(s): {', '.join(missing)}",
                action=self.name,
            )

        try:
            branch_id = int(row["branch_id"])
            report_date = date.fromisoformat(row["date"])
            revenue = Decimal(row["revenue"])
            headcount = int(row["headcount"])
        except (ValueError, InvalidOperation) as exc:
            ctx.data["validation_failed"] = True
            raise BusinessException(f"Report contains invalid field value: {exc}", action=self.name) from exc

        if branch_id <= 0:
            ctx.data["validation_failed"] = True
            raise BusinessException("branch_id must be a positive integer", action=self.name)
        if revenue < 0:
            ctx.data["validation_failed"] = True
            raise BusinessException("revenue must be greater than or equal to zero", action=self.name)
        if headcount <= 0:
            ctx.data["validation_failed"] = True
            raise BusinessException("headcount must be greater than zero", action=self.name)

        ctx.data["validated_report"] = {
            "branch_id": branch_id,
            "date": report_date.isoformat(),
            "revenue": revenue,
            "headcount": headcount,
        }
        ctx.data["validation_failed"] = False
