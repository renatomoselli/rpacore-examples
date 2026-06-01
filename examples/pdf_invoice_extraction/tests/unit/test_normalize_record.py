"""Unit tests for NormalizeRecord skill."""

from __future__ import annotations

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction

from skills.normalize_record import NormalizeRecord


class TestNormalizeRecord:
    """Tests for NormalizeRecord skill."""

    def _make_parsed_invoice(self, **overrides):
        """Create a valid parsed invoice dict with optional overrides."""
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

    def test_normalize_record_creation(self):
        """Test that a normalized record is created correctly."""
        parsed = self._make_parsed_invoice()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        record = ctx.data["normalized_record"]
        assert record["invoice_number"] == "INV-2024-001"
        assert record["date"] == "2024-01-15"
        assert record["vendor"] == "ACME CORP"
        assert record["currency"] == "USD"
        assert record["total"] == 250.00
        assert record["subtotal"] == 250.00
        assert record["line_items_count"] == 2

    def test_normalize_record_currency_default(self):
        """Test that currency defaults to USD when not detected."""
        parsed = self._make_parsed_invoice(currency=None)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["currency"] == "USD"

    def test_normalize_record_rounding(self):
        """Test that monetary values are rounded to 2 decimal places."""
        parsed = self._make_parsed_invoice(total=250.127, subtotal=250.123)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["total"] == 250.13
        assert ctx.data["normalized_record"]["subtotal"] == 250.12

    def test_normalize_record_validation_skip(self):
        """Test that validation failure short-circuits normalization."""
        parsed = self._make_parsed_invoice()
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={
                "parsed_invoice": parsed,
                "validation_failed": True,
            },
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)

        with pytest.raises(BusinessException, match="Validation failed"):
            skill.execute(ctx)

    def test_normalize_record_vendor_uppercase(self):
        """Test that vendor names are uppercased."""
        parsed = self._make_parsed_invoice(vendor="Euro Parts GmbH")
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["vendor"] == "EURO PARTS GMBH"

    def test_normalize_record_invoice_number_uppercase(self):
        """Test that invoice numbers are uppercased."""
        parsed = self._make_parsed_invoice(invoice_number="inv-2024-001")
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["invoice_number"] == "INV-2024-001"

    def test_normalize_record_description_lowercase(self):
        """Test that line item descriptions are lowercased."""
        parsed = self._make_parsed_invoice(
            line_items=[{"description": "Widget A", "quantity": 1, "unit_price": 10.00}]
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["line_items"][0]["description"] == "widget a"

    def test_normalize_record_line_items_count(self):
        """Test that line_items_count is set correctly."""
        parsed = self._make_parsed_invoice(
            line_items=[
                {"description": "Item 1", "quantity": 1, "unit_price": 10.00},
                {"description": "Item 2", "quantity": 2, "unit_price": 20.00},
                {"description": "Item 3", "quantity": 3, "unit_price": 30.00},
            ]
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["line_items_count"] == 3

    def test_normalize_record_missing_parsed_invoice(self):
        """Test that missing parsed_invoice raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)

        with pytest.raises(SystemException, match="parse_invoice"):
            skill.execute(ctx)

    def test_normalize_record_none_total_preserved(self):
        """Test that None total/subtotal values are preserved."""
        parsed = self._make_parsed_invoice(total=None, subtotal=None)
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["normalized_record"]["total"] is None
        assert ctx.data["normalized_record"]["subtotal"] is None

    def test_normalize_record_line_items_numeric_types(self):
        """Test that line item quantities and prices are numeric."""
        parsed = self._make_parsed_invoice(
            line_items=[{"description": "Widget", "quantity": 10, "unit_price": 15.5}]
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"parsed_invoice": parsed},
        )
        skill = NormalizeRecord(name="normalize_record", execution_order=1)
        skill.execute(ctx)

        item = ctx.data["normalized_record"]["line_items"][0]
        assert isinstance(item["quantity"], float)
        assert isinstance(item["unit_price"], float)
        assert item["quantity"] == 10.0
        assert item["unit_price"] == 15.5
