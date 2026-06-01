from __future__ import annotations

from decimal import Decimal

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class ClassifyOutcome(Skill):
    """Classify the current payment as matched, missing, or amount mismatch."""

    def execute(self, ctx: ProcessContext) -> None:
        payment = ctx.data.get("current_payment")
        candidates = ctx.data.get("bank_candidates")
        if not isinstance(payment, dict):
            raise SystemException("No current_payment in context", action=self.name)
        if not isinstance(candidates, list):
            raise SystemException("No bank_candidates in context", action=self.name)

        if not candidates:
            ctx.data["reconciliation_result"] = _result(payment, "missing_from_bank", None)
            raise BusinessException(
                f"Payment {payment.get('payment_id')} missing from bank statement",
                action=self.name,
            )

        expected_amount = payment.get("amount")
        if not isinstance(expected_amount, Decimal):
            raise SystemException("Current payment amount has unexpected type", action=self.name)

        for candidate in candidates:
            candidate_amount = candidate.get("amount")
            if not isinstance(candidate_amount, Decimal):
                raise SystemException("Bank candidate amount has unexpected type", action=self.name)
            if candidate_amount == expected_amount:
                ctx.data["reconciliation_result"] = _result(payment, "matched", candidate)
                return

        ctx.data["reconciliation_result"] = _result(payment, "amount_mismatch", candidates[0])
        raise BusinessException(
            f"Payment {payment.get('payment_id')} amount mismatch for reference {payment.get('reference')}",
            action=self.name,
        )


def _result(payment: dict, status: str, bank_entry: dict | None) -> dict[str, object]:
    return {
        "payment_id": payment.get("payment_id", ""),
        "date": payment.get("date", ""),
        "reference": payment.get("reference", ""),
        "vendor": payment.get("vendor", ""),
        "internal_amount": payment.get("amount", ""),
        "bank_amount": bank_entry.get("amount", "") if bank_entry else "",
        "bank_date": bank_entry.get("posted_date", "") if bank_entry else "",
        "status": status,
        "reason_code": "" if status == "matched" else status,
    }
