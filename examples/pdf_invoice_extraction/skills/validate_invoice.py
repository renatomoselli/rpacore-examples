"""Validate parsed invoice data against business rules."""

from __future__ import annotations

from datetime import date, datetime

from rpacore import BusinessException, ProcessContext, Skill, get_logger

from skills._currency import try_parse_currency_number

logger = get_logger(__name__)

# Business rules
_TOLERANCE_PER_ITEM = 0.02
_MAX_TOTAL_TOLERANCE = 1.00


class ValidateInvoice(Skill):
    """Validate parsed invoice data against business rules."""

    def execute(self, ctx: ProcessContext) -> None:
        parsed_invoice = ctx.require_state("parsed_invoice", dict, action=self.name)
        errors: list[str] = []

        if not parsed_invoice.get("invoice_number"):
            errors.append("Missing required field: invoice_number")

        if not parsed_invoice.get("date"):
            errors.append("Missing required field: date")
        elif not self._validate_date(str(parsed_invoice["date"])):
            errors.append(f"Invalid or future date: {parsed_invoice['date']}")

        if not parsed_invoice.get("vendor"):
            errors.append("Missing required field: vendor")

        total = parsed_invoice.get("total")
        subtotal_value = parsed_invoice.get("subtotal")
        line_items = parsed_invoice.get("line_items", [])

        if not line_items:
            errors.append("Has total but no line items" if total else "No line items")
        if not total:
            errors.append(
                "Has line items but no total"
                if line_items
                else "Missing required field: total"
            )

        if line_items and total:
            computed_subtotal = sum(
                item.get("quantity", 0) * item.get("unit_price", 0)
                for item in line_items
            )
            tolerance = min(
                _TOLERANCE_PER_ITEM * len(line_items),
                _MAX_TOTAL_TOLERANCE,
            )
            try:
                reported_total = self._parse_money(total)
                if abs(computed_subtotal - reported_total) > tolerance:
                    errors.append(
                        f"Total ({reported_total:.2f}) does not match line item "
                        f"subtotal ({computed_subtotal:.2f}) - tolerance: {tolerance:.2f}"
                    )
                if subtotal_value not in (None, ""):
                    reported_subtotal = self._parse_money(subtotal_value)
                    if abs(computed_subtotal - reported_subtotal) > tolerance:
                        errors.append(
                            f"Subtotal ({reported_subtotal:.2f}) does not match line item "
                            f"subtotal ({computed_subtotal:.2f}) - tolerance: {tolerance:.2f}"
                        )
            except (ValueError, TypeError):
                errors.append(
                    f"Invalid total or subtotal format: total={total}, subtotal={subtotal_value}"
                )

        if errors:
            ctx.state["validation_failed"] = True
            raise BusinessException(
                f"Validation failed: {'; '.join(errors)}",
                action=self.name,
                stop=True,
            )

        ctx.state["validation_failed"] = False

    @staticmethod
    def _parse_money(value: object) -> float:
        """Parse a money value after stripping supported currency symbols."""
        parsed = try_parse_currency_number(value)
        if parsed is None:
            raise ValueError(f"Invalid money value: {value!r}")
        return parsed

    def _validate_date(self, date_str: str) -> bool:
        """Check that a date string is parseable and not in the future."""
        if not date_str:
            return False

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(date_str, fmt).date()
                return dt <= date.today()
            except ValueError:
                continue

        return False
