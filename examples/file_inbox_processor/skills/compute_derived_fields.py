from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from rpacore import ProcessContext, Skill, Status, SystemException


class ComputeDerivedFields(Skill):
    """Calculate business metrics for the validated branch report."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return

        report = ctx.require_state("validated_report", dict, action=self.name)
        if not isinstance(report, dict):
            raise SystemException("No validated report in context", action=self.name)

        revenue = report["revenue"]
        headcount = report["headcount"]
        if not isinstance(revenue, str) or not isinstance(headcount, int):
            raise SystemException("Validated report has unexpected types", action=self.name)
        if headcount == 0:
            raise SystemException(
                "headcount must be greater than zero for revenue_per_headcount calculation",
                action=self.name,
            )

        try:
            revenue_amount = Decimal(revenue)
        except Exception as exc:
            raise SystemException("Validated report has unexpected types", action=self.name) from exc

        revenue_per_headcount = (revenue_amount / Decimal(headcount)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        enriched = dict(report)
        enriched["revenue_per_headcount"] = str(revenue_per_headcount)
        ctx.state["processed_report"] = enriched
