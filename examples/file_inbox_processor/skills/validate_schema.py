from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from rpacore import BusinessException, ProcessContext, Skill, SystemException

REQUIRED_COLUMNS = ("branch_id", "date", "revenue", "headcount")


class ValidateSchema(Skill):
    """Validate report schema and business rules."""

    def execute(self, ctx: ProcessContext) -> None:
        rows = ctx.require_state("report_rows", action=self.name)
        if rows is None:
            raise SystemException("No report rows in context", action=self.name)
        if not isinstance(rows, list):
            raise SystemException(
                f"Expected report_rows to be a list, got {type(rows).__name__}",
                action=self.name,
            )
        if not rows:
            ctx.state["validation_failed"] = True
            raise BusinessException(
                "Report must contain exactly one data row, got 0 rows",
                action=self.name,
                stop=True,
            )
        if len(rows) != 1:
            ctx.state["validation_failed"] = True
            raise BusinessException(
                f"Report must contain exactly one data row, got {len(rows)}",
                action=self.name,
                stop=True,
            )

        row = rows[0]
        missing = [column for column in REQUIRED_COLUMNS if column not in row or row[column] == ""]
        if missing:
            ctx.state["validation_failed"] = True
            raise BusinessException(
                f"Report missing required column(s): {', '.join(missing)}",
                action=self.name,
                stop=True,
            )

        try:
            branch_id = int(row["branch_id"])
            report_date = date.fromisoformat(row["date"])
            revenue = Decimal(row["revenue"])
            headcount = int(row["headcount"])
        except (ValueError, InvalidOperation) as exc:
            ctx.state["validation_failed"] = True
            raise BusinessException(
                f"Report contains invalid field value: {exc}",
                action=self.name,
                stop=True,
            ) from exc

        if branch_id <= 0:
            ctx.state["validation_failed"] = True
            raise BusinessException("branch_id must be a positive integer", action=self.name, stop=True)
        if revenue < 0:
            ctx.state["validation_failed"] = True
            raise BusinessException("revenue must be greater than or equal to zero", action=self.name, stop=True)
        if headcount <= 0:
            ctx.state["validation_failed"] = True
            raise BusinessException("headcount must be greater than zero", action=self.name, stop=True)

        ctx.state["validated_report"] = {
            "branch_id": branch_id,
            "date": report_date.isoformat(),
            "revenue": str(revenue),
            "headcount": headcount,
        }
        ctx.state["validation_failed"] = False
        ctx.transaction.metadata["branch_id"] = branch_id
        ctx.transaction.metadata["report_date"] = report_date.isoformat()
