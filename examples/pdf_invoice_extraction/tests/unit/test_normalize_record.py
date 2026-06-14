"""Unit tests for NormalizeRecord skill."""

from __future__ import annotations

import pytest

from rpacore import ProcessContext, Status, SystemException, Transaction

from skills.normalize_record import NormalizeRecord

class TestNormalizeRecord:
    """Tests for NormalizeRecord skill."""

    def _make_parsed_invoice(self, **overrides):
        base = {
            "invoice_number": "inv-2024-001",
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

    def _run_skill(self, **state_overrides):
        parsed = state_overrides.pop("parsed_invoice", self._make_parsed_invoice())
        tx = Transaction(reference="test", skills=[NormalizeRecord(name="normalize_record", execution_order=1)])
        tx.state["parsed_invoice"] = parsed
        tx.state.update(state_overrides)
        ctx = ProcessContext(transaction=tx, config={})
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)
        return tx

    def test_normalize_record_creation(self):
        tx = self._run_skill()
        record = tx.state["normalized_record"]
        assert record["invoice_number"] == "INV-2024-001"
        assert record["date"] == "2024-01-15"
        assert record["vendor"] == "ACME CORP"
        assert record["currency"] == "USD"
        assert record["total"] == 250.00
        assert record["subtotal"] == 250.00
        assert record["line_items_count"] == 2

    def test_normalize_record_currency_default(self):
        tx = self._run_skill(parsed_invoice=self._make_parsed_invoice(currency=None))
        assert tx.state["normalized_record"]["currency"] == "USD"

    def test_normalize_record_currency_symbols_to_iso_codes(self):
        assert self._run_skill(
            parsed_invoice=self._make_parsed_invoice(currency="$")
        ).state["normalized_record"]["currency"] == "USD"
        assert self._run_skill(
            parsed_invoice=self._make_parsed_invoice(currency="R$")
        ).state["normalized_record"]["currency"] == "BRL"
        assert self._run_skill(
            parsed_invoice=self._make_parsed_invoice(currency="€")
        ).state["normalized_record"]["currency"] == "EUR"

    def test_normalize_record_rounding(self):
        tx = self._run_skill(parsed_invoice=self._make_parsed_invoice(total=250.127, subtotal=250.123))
        assert tx.state["normalized_record"]["total"] == 250.13
        assert tx.state["normalized_record"]["subtotal"] == 250.12

    def test_normalize_record_validation_skip(self):
        """Validation failure causes Status.SKIPPED, not BusinessException."""
        tx = Transaction(reference="test", skills=[NormalizeRecord(name="normalize_record", execution_order=1)])
        tx.state["parsed_invoice"] = self._make_parsed_invoice()
        tx.state["validation_failed"] = True
        ctx = ProcessContext(transaction=tx, config={})
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert skill.status == Status.SKIPPED
        assert "normalized_record" not in tx.state

    def test_normalize_record_vendor_uppercase(self):
        tx = self._run_skill(parsed_invoice=self._make_parsed_invoice(vendor="Euro Parts GmbH"))
        assert tx.state["normalized_record"]["vendor"] == "EURO PARTS GMBH"

    def test_normalize_record_invoice_number_uppercase(self):
        tx = self._run_skill()
        assert tx.state["normalized_record"]["invoice_number"] == "INV-2024-001"

    def test_normalize_record_description_lowercase(self):
        tx = self._run_skill(
            parsed_invoice=self._make_parsed_invoice(
                line_items=[{"description": "Widget A", "quantity": 1, "unit_price": 10.00}]
            )
        )
        assert tx.state["normalized_record"]["line_items"][0]["description"] == "widget a"

    def test_normalize_record_line_items_count(self):
        tx = self._run_skill(
            parsed_invoice=self._make_parsed_invoice(
                line_items=[
                    {"description": "Item 1", "quantity": 1, "unit_price": 10.00},
                    {"description": "Item 2", "quantity": 2, "unit_price": 20.00},
                    {"description": "Item 3", "quantity": 3, "unit_price": 30.00},
                ]
            )
        )
        assert tx.state["normalized_record"]["line_items_count"] == 3

    def test_normalize_record_missing_parsed_invoice(self):
        tx = Transaction(reference="test", skills=[NormalizeRecord(name="normalize_record", execution_order=1)])
        ctx = ProcessContext(transaction=tx, config={})
        skill = NormalizeRecord(name="normalize_record", execution_order=1)

        with pytest.raises(SystemException, match="parsed_invoice"):
            skill.execute(ctx)

    def test_normalize_record_none_total_preserved(self):
        tx = self._run_skill(parsed_invoice=self._make_parsed_invoice(total=None, subtotal=None))
        assert tx.state["normalized_record"]["total"] is None
        assert tx.state["normalized_record"]["subtotal"] is None

    def test_normalize_record_line_items_numeric_types(self):
        tx = self._run_skill(
            parsed_invoice=self._make_parsed_invoice(
                line_items=[{"description": "Widget", "quantity": 10, "unit_price": 15.5}]
            )
        )
        item = tx.state["normalized_record"]["line_items"][0]
        assert isinstance(item["quantity"], float)
        assert isinstance(item["unit_price"], float)
        assert item["quantity"] == 10.0
        assert item["unit_price"] == 15.5
