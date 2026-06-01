from __future__ import annotations

from rpacore import ProcessContext, Skill, SystemException


class MatchTransaction(Skill):
    """Find candidate bank entries for the current internal payment."""

    def execute(self, ctx: ProcessContext) -> None:
        payment = ctx.data.get("current_payment")
        bank_by_reference = ctx.data.get("bank_by_reference")
        if not isinstance(payment, dict):
            raise SystemException("No current_payment in context", action=self.name)
        if not isinstance(bank_by_reference, dict):
            raise SystemException("No bank statement index in context", action=self.name)

        reference = payment.get("reference")
        if not isinstance(reference, str) or not reference:
            raise SystemException("Current payment missing reference", action=self.name)

        ctx.data["bank_candidates"] = bank_by_reference.get(reference, [])
