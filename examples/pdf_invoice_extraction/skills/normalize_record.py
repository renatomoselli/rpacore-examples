"""Normalize parsed invoice data for CSV output."""

from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class NormalizeRecord(Skill):
    """Normalize parsed invoice data for consistent CSV output.

    Checks for validation failures first (short-circuit pattern):
    if validate_invoice set validation_failed=True, this skill raises
    SystemException to stop execution.

    Normalization steps:
    - Defaults currency to USD if not detected
    - Rounds monetary values to 2 decimal places
    - Standardizes line item format (numeric types, lowercase description)
    - Uppercases vendor and invoice number for consistency

    Expected input keys in ctx.data:
        - parsed_invoice: dict — Parsed invoice fields from parse_invoice
        - validation_failed: bool (optional) — Set by validate_invoice

    Sets on ctx.data:
        - normalized_record: dict — Normalized invoice record ready for CSV
    """

    def execute(self, ctx: ProcessContext) -> None:
        parsed_invoice = ctx.data.get("parsed_invoice")
        if parsed_invoice is None:
            raise SystemException(
                "No parsed_invoice in context — parse_invoice must run first",
                action=self.name,
            )

        # Short-circuit on validation failure (validation_failed flag pattern)
        if ctx.data.get("validation_failed", False):
            raise BusinessException(
                "Validation failed — skipping normalization",
                action=self.name,
            )

        record = self._normalize(parsed_invoice)
        ctx.data["normalized_record"] = record
        logger.info(
            "Normalized invoice: %s",
            record.get("invoice_number", "unknown"),
        )

    def _normalize(self, invoice: dict) -> dict:
        """Apply normalization rules to a parsed invoice."""
        # Default currency to USD if not detected
        currency = invoice.get("currency") or "USD"

        # Handle None values for total/subtotal — preserve as None
        raw_total = invoice.get("total")
        raw_subtotal = invoice.get("subtotal")

        # Strip currency symbols before numeric conversion
        # (parse_invoice stores totals as strings like "$275.00")
        _CURRENCY_SYMBOLS = ["$", "€", "£", "¥", "R$"]

        def _to_float(val: str | float | int | None) -> float | None:
            if val is None:
                return None
            s = str(val)
            for sym in _CURRENCY_SYMBOLS:
                s = s.replace(sym, "")
            s = s.replace(",", "").strip()
            try:
                return float(s)
            except (ValueError, TypeError):
                return None

        # Round monetary values to 2 decimal places (only if not None)
        total = _to_float(raw_total)
        if total is not None:
            total = round(total, 2)

        subtotal = _to_float(raw_subtotal)
        if subtotal is not None:
            subtotal = round(subtotal, 2)
        else:
            # Default subtotal to total if not provided
            subtotal = total

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
