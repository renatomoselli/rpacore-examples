"""Unit tests for ValidateInvoice skill."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction

from skills.validate_invoice import ValidateInvoice

class TestValidateInvoice:
    """Tests for ValidateInvoice skill."""

    def _make_parsed_invoice(self, **overrides):
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

    def _run_skill(self, parsed_invoice=None):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        if parsed_invoice is not None:
            tx.state["parsed_invoice"] = parsed_invoice
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)
        skill.execute(ctx)
        return tx

    def test_validate_invoice_passes(self):
        tx = self._run_skill(self._make_parsed_invoice())
        assert tx.state.get("validation_failed") is False

    def test_validate_invoice_missing_invoice_number(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(invoice_number="")
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="invoice_number"):
            skill.execute(ctx)
        assert tx.state.get("validation_failed") is True

    def test_validate_invoice_missing_date(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(date="")
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="date"):
            skill.execute(ctx)

    def test_validate_invoice_future_date(self):
        future_date = (date.today() + timedelta(days=1)).isoformat()
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(date=future_date)
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="future date"):
            skill.execute(ctx)

    def test_validate_invoice_total_mismatch(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(total=999.99)
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="does not match"):
            skill.execute(ctx)

    def test_validate_invoice_subtotal_mismatch(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(subtotal=200.00)
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="Subtotal"):
            skill.execute(ctx)

    def test_validate_invoice_total_within_tolerance(self):
        tx = self._run_skill(self._make_parsed_invoice(total=250.03))
        assert tx.state.get("validation_failed") is False

    def test_validate_invoice_empty_vendor(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(vendor="")
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="vendor"):
            skill.execute(ctx)

    def test_validate_invoice_total_without_line_items(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(line_items=[], total=100.00)
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="no line items"):
            skill.execute(ctx)

    @pytest.mark.parametrize("total", [None, ""])
    def test_validate_invoice_line_items_without_total(self, total):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(total=total)
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(BusinessException, match="line items but no total"):
            skill.execute(ctx)

    def test_validate_invoice_requires_items_and_total(self):
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(line_items=[], total="")
        ctx = ProcessContext(transaction=tx, config={})

        with pytest.raises(BusinessException, match="No line items.*total"):
            ValidateInvoice(name="validate_invoice", execution_order=1).execute(ctx)

    def test_validate_invoice_no_parsed_invoice(self):
        """Missing parsed_invoice raises SystemException (via require_state)."""
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        ctx = ProcessContext(transaction=tx, config={})
        skill = ValidateInvoice(name="validate_invoice", execution_order=1)

        with pytest.raises(SystemException, match="parsed_invoice"):
            skill.execute(ctx)

    def test_validate_invoice_tolerance_scales_with_items(self):
        tx = self._run_skill(self._make_parsed_invoice(
            line_items=[{"description": f"Item {i}", "quantity": 1, "unit_price": 10.00} for i in range(5)],
            total=50.09,
        ))
        assert tx.state.get("validation_failed") is False

    def test_validate_invoice_tolerance_is_capped_for_large_invoices(self):
        line_items = [
            {"description": f"Item {i}", "quantity": 1, "unit_price": 10.00}
            for i in range(100)
        ]
        tx = Transaction(reference="test", skills=[ValidateInvoice(name="validate_invoice", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice(
            line_items=line_items,
            total=1001.50,
        )
        ctx = ProcessContext(transaction=tx, config={})

        with pytest.raises(BusinessException, match="does not match"):
            ValidateInvoice(name="validate_invoice", execution_order=1).execute(ctx)

    @pytest.mark.parametrize("value", ["R100.00", "R$100.00", "100.00 USD", "EUR 100.00"])
    def test_parse_money_strips_only_currency_affixes(self, value):
        assert ValidateInvoice._parse_money(value) == 100.00
        with pytest.raises(ValueError):
            ValidateInvoice._parse_money("1R00.00")
