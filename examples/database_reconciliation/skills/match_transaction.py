from __future__ import annotations

from rpacore import ProcessContext, Skill, SystemException


class MatchTransaction(Skill):
    """Find candidate bank entries for the current internal payment."""

    def execute(self, ctx: ProcessContext) -> None:
        payment = ctx.require_state("current_payment", dict, action=self.name)
        bank_by_reference = ctx.require_state("bank_by_reference", dict, action=self.name)

        reference = payment.get("reference")
        if not isinstance(reference, str) or not reference:
            raise SystemException("Current payment missing reference", action=self.name)

        ctx.state["bank_candidates"] = bank_by_reference.get(reference, [])
