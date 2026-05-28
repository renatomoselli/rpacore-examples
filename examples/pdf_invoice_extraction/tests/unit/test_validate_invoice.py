"""Unit tests for ValidateInvoice skill."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from oref import BusinessException, ProcessContext, SystemException, Transaction

from skills.validate_invoice import ValidateInvoice


class TestValidateInvoice:
    """Tests for ValidateInvoice skill."""

    def _make_parsed_invoice(self, **overrides):
        """Create a valid parsed invoice dict with optional overrides."""
        base = {
            "invoice_number": "INV-2024-001",
            "date": "2024-01-15",
            "vendor": "Acme Corp",
            "line_items": [
                {"description": "Widget A", "quantity": 10, "unit_price": 15.00},
                {"description": "Widget B", "quantity": 5, "unit_price": 20.00},
            ],
            "total": 250.00,
            "currency": "USD",
        }
        base.update(overrides)
        return base

    def test_validate_invoice_passes(self):
        """Test that a valid invoice passes validation."""
        parsed = self._make_parsed_invoice()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data.get("validation_failed") is False

    def test_validate_invoice_missing_invoice_number(self):
        """Test that missing invoice number raises BusinessException."""
        parsed = self._make_parsed_invoice(invoice_number="")
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="invoice_number"):
            skill.execute(ctx)
        assert ctx.data.get("validation_failed") is True

    def test_validate_invoice_missing_date(self):
        """Test that missing date raises BusinessException."""
        parsed = self._make_parsed_invoice(date="")
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="date"):
            skill.execute(ctx)

    def test_validate_invoice_future_date(self):
        """Test that future dates raise BusinessException."""
        future_date = (date.today() + timedelta(days=1)).isoformat()
        parsed = self._make_parsed_invoice(date=future_date)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="future date"):
            skill.execute(ctx)

    def test_validate_invoice_total_mismatch(self):
        """Test that total mismatch raises BusinessException with tolerance."""
        parsed = self._make_parsed_invoice(total=999.99)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="does not match"):
            skill.execute(ctx)

    def test_validate_invoice_total_within_tolerance(self):
        """Test that total within tolerance passes validation."""
        # 2 items * 0.02 tolerance = 0.04
        parsed = self._make_parsed_invoice(total=250.03)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data.get("validation_failed") is False

    def test_validate_invoice_empty_vendor(self):
        """Test that empty vendor raises BusinessException."""
        parsed = self._make_parsed_invoice(vendor="")
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="vendor"):
            skill.execute(ctx)

    def test_validate_invoice_total_without_line_items(self):
        """Test that having total but no line items fails validation."""
        parsed = self._make_parsed_invoice(line_items=[], total=100.00)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="no line items"):
            skill.execute(ctx)

    def test_validate_invoice_no_parsed_invoice(self):
        """Test that missing parsed_invoice raises BusinessException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="parse_invoice"):
            skill.execute(ctx)

    def test_validate_invoice_tolerance_scales_with_items(self):
        """Test that tolerance scales with number of line items."""
        # 5 items * 0.02 = 0.10 tolerance
        parsed = self._make_parsed_invoice(
            line_items=[
                {"description": f"Item {i}", "quantity": 1, "unit_price": 10.00}
                for i in range(5)
            ],
            total=50.09,  # within 0.10 tolerance
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data.get("validation_failed") is False
