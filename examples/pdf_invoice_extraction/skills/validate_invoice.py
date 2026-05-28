"""Validate parsed invoice data against business rules."""

from __future__ import annotations

import logging
from datetime import date, datetime

from oref import BusinessException, ProcessContext, Skill, get_logger

logger = get_logger(__name__)

# Business rules
_TOLERANCE_PER_ITEM = 0.02  # Allow 2 cent rounding tolerance per line item


class ValidateInvoice(Skill):
    """Validate parsed invoice data against business rules.

    Checks:
    - Required fields present (invoice_number, date, vendor)
    - Date is parseable and not in the future
    - Total matches line item subtotal (within tolerance)
    - No total without line items
    - Vendor is non-empty

    Sets ctx.data["validation_failed"] = True before raising BusinessException
    so that normalize_record can check the flag and short-circuit.

    Expected input keys in ctx.data:
        - parsed_invoice: dict — Parsed invoice fields from parse_invoice

    Sets on ctx.data:
        - validation_failed: bool — True if any validation rule failed
    """

    def execute(self, ctx: ProcessContext) -> None:
        parsed_invoice = ctx.data.get("parsed_invoice")
        if parsed_invoice is None:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                "No parsed_invoice in context — parse_invoice must run first",
                action=self.name,
            )

        # Run all validation checks
        errors: list[str] = []

        # Check required fields
        if not parsed_invoice.get("invoice_number"):
            errors.append("Missing required field: invoice_number")

        if not parsed_invoice.get("date"):
            errors.append("Missing required field: date")
        else:
            # Validate date is parseable and not in the future
            if not self._validate_date(parsed_invoice["date"]):
                errors.append(f"Invalid or future date: {parsed_invoice['date']}")

        if not parsed_invoice.get("vendor"):
            errors.append("Missing required field: vendor")

        # Check total vs line items
        total = parsed_invoice.get("total")
        line_items = parsed_invoice.get("line_items", [])

        # Total without line items is an error
        if total is not None and not line_items:
            errors.append("Has total but no line items")

        # Check total matches line items
        if line_items and total is not None:
            subtotal = sum(
                item.get("quantity", 0) * item.get("unit_price", 0)
                for item in line_items
            )
            try:
                reported_total = float(str(total).replace(",", "").replace("$", "").replace("€", "").replace("£", "").replace("¥", "").replace("R", "").strip())
                tolerance = _TOLERANCE_PER_ITEM * len(line_items)
                if abs(subtotal - reported_total) > tolerance:
                    errors.append(
                        f"Total ({reported_total:.2f}) does not match line item "
                        f"subtotal ({subtotal:.2f}) — tolerance: {tolerance:.2f}"
                    )
            except (ValueError, TypeError):
                errors.append(f"Invalid total format: {total}")

        # Record results
        if errors:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                f"Validation failed: {'; '.join(errors)}",
                action=self.name,
            )

        ctx.data["validation_failed"] = False

    def _validate_date(self, date_str: str) -> bool:
        """Check that a date string is parseable and not in the future."""
        if not date_str:
            return False

        # Try standard formats
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(date_str, fmt).date()
                return dt <= date.today()
            except ValueError:
                continue

        return False
