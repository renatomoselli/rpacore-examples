from __future__ import annotations

from decimal import Decimal

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class ClassifyOutcome(Skill):
    """Classify the current payment as matched, missing, or amount mismatch."""

    def execute(self, ctx: ProcessContext) -> None:
        payment = ctx.require_state("current_payment", dict, action=self.name)
        candidates = ctx.require_state("bank_candidates", list, action=self.name)

        if not candidates:
            ctx.state["reconciliation_result"] = _result(payment, "missing_from_bank", None)
            raise BusinessException(
                f"Payment {payment.get('payment_id')} missing from bank statement",
                action=self.name,
            )

        expected_amount_str = payment.get("amount")
        if not isinstance(expected_amount_str, str):
            ctx.state["reconciliation_result"] = _result(payment, "type_error", None)
            raise SystemException(
                f"Current payment amount must be str, got {expected_amount_str!r}",
                action=self.name,
            )
        expected_amount = Decimal(expected_amount_str)

        closest_candidate: dict | None = None
        closest_difference: Decimal | None = None
        for candidate in candidates:
            candidate_amount_str = candidate.get("amount")
            if not isinstance(candidate_amount_str, str):
                ctx.state["reconciliation_result"] = _result(payment, "type_error", candidate)
                raise SystemException(
                    f"Bank candidate amount must be str, got {candidate_amount_str!r}",
                    action=self.name,
                )
            candidate_amount = Decimal(candidate_amount_str)
            if candidate_amount == expected_amount:
                ctx.state["reconciliation_result"] = _result(payment, "matched", candidate)
                return
            difference = abs(candidate_amount - expected_amount)
            if closest_difference is None or difference < closest_difference:
                closest_candidate = candidate
                closest_difference = difference

        ctx.state["reconciliation_result"] = _result(payment, "amount_mismatch", closest_candidate)
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
