"""Normalize parsed invoice data for CSV output."""

from __future__ import annotations

from rpacore import ProcessContext, Skill, Status, SystemException, get_logger

from skills._currency import try_parse_currency_number

logger = get_logger(__name__)

class NormalizeRecord(Skill):
    """Normalize parsed invoice data for consistent CSV output.

    Checks for validation failures first (defensive backstop):
    if validate_invoice set validation_failed=True, this skill
    sets self.status = Status.SKIPPED and returns.

    Normalization steps:
    - Defaults currency to USD if not detected
    - Rounds monetary values to 2 decimal places
    - Standardizes line item format (numeric types, lowercase description)
    - Uppercases vendor and invoice number for consistency
    """

    def execute(self, ctx: ProcessContext) -> None:
        parsed_invoice = ctx.require_state("parsed_invoice", dict, action=self.name)

        # Defensive backstop on validation failure (BusinessException(stop=True)
        # should already have halted the Engine, but guard for edge cases)
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return

        record = self._normalize(parsed_invoice)
        ctx.state["normalized_record"] = record
        logger.info(
            "Normalized invoice: %s",
            record.get("invoice_number", "unknown"),
        )

    def _normalize(self, invoice: dict) -> dict:
        """Apply normalization rules to a parsed invoice."""
        # Default currency to USD if not detected
        currency = self._normalize_currency(invoice.get("currency") or "USD")

        # Handle None values for total/subtotal — preserve as None
        raw_total = invoice.get("total")
        raw_subtotal = invoice.get("subtotal")

        def _to_float(val: str | float | int | None) -> float | None:
            if val is None:
                return None
            return try_parse_currency_number(val)

        # Round monetary values to 2 decimal places (only if not None)
        total = _to_float(raw_total)
        if total is not None:
            total = round(total, 2)

        subtotal = _to_float(raw_subtotal)
        if subtotal is not None:
            subtotal = round(subtotal, 2)
        elif total is not None:
            logger.warning(
                "Subtotal missing; deriving it from %d parsed line items.",
                len(invoice.get("line_items", [])),
            )
            subtotal = round(
                sum(
                    float(item.get("quantity", 0))
                    * float(item.get("unit_price", 0))
                    for item in invoice.get("line_items", [])
                ),
                2,
            )
        else:
            subtotal = None

        # Standardize line items
        line_items = []
        for item in invoice.get("line_items", []):
            line_items.append({
                "description": str(item.get("description", "")).strip().lower(),
                "quantity": round(float(item.get("quantity", 0)), 2),
                "unit_price": round(float(item.get("unit_price", 0)), 2),
            })

        return {
            "invoice_number": str(invoice.get("invoice_number", "")).strip().upper(),
            "date": str(invoice.get("date", "")).strip(),
            "vendor": str(invoice.get("vendor", "")).strip().upper(),
            "line_items": line_items,
            "line_items_count": len(line_items),
            "subtotal": subtotal,
            "total": total,
            "currency": currency,
        }

    @staticmethod
    def _normalize_currency(currency: object) -> str:
        """Normalize currency symbols to ISO 4217-style codes."""
        mapping = {
            "$": "USD",
            "USD": "USD",
            "R$": "BRL",
            "R": "BRL",
            "BRL": "BRL",
            "€": "EUR",
            "â‚¬": "EUR",
            "EUR": "EUR",
            "£": "GBP",
            "Â£": "GBP",
            "GBP": "GBP",
            "¥": "JPY",
            "Â¥": "JPY",
            "JPY": "JPY",
        }
        raw_value = str(currency).strip()
        if raw_value in mapping:
            return mapping[raw_value]
        value = raw_value.upper()
        return mapping.get(value, value or "USD")
