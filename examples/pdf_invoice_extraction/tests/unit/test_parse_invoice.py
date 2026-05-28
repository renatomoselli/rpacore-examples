"""Unit tests for ParseInvoice skill."""

from __future__ import annotations

import pytest

from oref import ProcessContext, SystemException, Transaction

from skills.parse_invoice import ParseInvoice


class TestParseInvoice:
    """Tests for ParseInvoice skill."""

    def test_parse_invoice_field_extraction(self, sample_invoice_text: str):
        """Test extraction of all invoice fields."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": sample_invoice_text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        parsed = ctx.data["parsed_invoice"]
        assert parsed["invoice_number"] == "INV-2024-001"
        assert parsed["date"] == "2024-01-15"
        assert parsed["vendor"] == "Acme Corp"
        assert len(parsed["line_items"]) == 2
        assert parsed["total"] == "$275.00"
        assert parsed["currency"] == "$"

    def test_parse_invoice_date_formats(self):
        """Test various date formats are normalized to YYYY-MM-DD."""
        test_cases = [
            ("Invoice Number: INV-001\nDate: 2024-03-15", "2024-03-15"),
            ("Invoice Number: INV-001\nDate: 15/03/2024", "2024-03-15"),
            ("Invoice Number: INV-001\nDate: 03/15/2024", "2024-03-15"),
            ("Invoice Number: INV-001\nDate: 15-03-2024", "2024-03-15"),
            ("Invoice Number: INV-001\nDate: 01-02-2024", "2024-02-01"),
        ]
        for text, expected_date in test_cases:
            ctx = ProcessContext(
                transaction=Transaction(reference="test", skills=[]),
                data={"pdf_text": text},
            )
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert ctx.data["parsed_invoice"]["date"] == expected_date, f"Failed for text: {text}"

    def test_parse_invoice_currency_detection_from_total(self):
        """Test currency detected from total string first."""
        texts = [
            ("Total: €100.00", "€"),
            ("Total: $50.00", "$"),
            ("Total: £75.00", "£"),
            ("Total: ¥1000", "¥"),
        ]
        for text, expected_currency in texts:
            ctx = ProcessContext(
                transaction=Transaction(reference="test", skills=[]),
                data={"pdf_text": text},
            )
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert ctx.data["parsed_invoice"]["currency"] == expected_currency

    def test_parse_invoice_empty_text(self):
        """Test that empty text raises SystemException."""
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": ""},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)

        with pytest.raises(SystemException, match="No PDF text"):
            skill.execute(ctx)

    def test_parse_invoice_no_line_items(self):
        """Test parsing when no line items are present."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: $100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["parsed_invoice"]["line_items"] == []

    def test_parse_invoice_vendor_casing_preserved(self):
        """Test that vendor casing is preserved from PDF text."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Euro Parts GmbH\nTotal: $100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["parsed_invoice"]["vendor"] == "Euro Parts GmbH"

    def test_parse_invoice_multiline_items(self):
        """Test parsing multiple line items with position-based parsing."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Item Qty Unit Price\n"
            "Office Chair 3 150.00\n"
            "Desk Lamp 5 25.00\n"
            "Notebook Pack 10 8.50\n"
            "Total: $660.00"
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = ctx.data["parsed_invoice"]["line_items"]
        assert len(items) == 3
        assert items[0]["description"] == "Office Chair"
        assert items[0]["quantity"] == 3
        assert items[0]["unit_price"] == 150.00
        assert items[1]["description"] == "Desk Lamp"
        assert items[2]["description"] == "Notebook Pack"

    def test_parse_invoice_line_items_with_numbers_in_description(self):
        """Test that descriptions with numbers don't corrupt parsing."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Item Qty Unit Price\n"
            "Model 3 Adapter 10 15.00\n"
            "Total: $150.00"
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = ctx.data["parsed_invoice"]["line_items"]
        assert len(items) == 1
        # Description should not contain the qty/price numbers
        assert "Adapter" in items[0]["description"]
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 15.00

    def test_parse_invoice_default_currency(self):
        """Test that currency defaults to USD when no symbol found."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: 100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["parsed_invoice"]["currency"] == "USD"

    def test_parse_invoice_net_total_vs_net_income(self):
        """Test that 'net total' is matched but 'net income' is not."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Subtotal: $100.00\n"
            "Tax: $10.00\n"
            "Net Total: $110.00"
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["parsed_invoice"]["total"] == "$110.00"

    def test_parse_invoice_invoice_number_variations(self):
        """Test various invoice number label formats."""
        labels = [
            "Invoice Number: INV-001",
            "Invoice #: INV-002",
            "Inv. No: INV-003",
            "Num#: INV-004",
        ]
        for label in labels:
            text = f"{label}\nDate: 2024-01-15\nBill From: Test Corp\nTotal: $100.00"
            ctx = ProcessContext(
                transaction=Transaction(reference="test", skills=[]),
                data={"pdf_text": text},
            )
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert ctx.data["parsed_invoice"]["invoice_number"] == label.split(":")[-1].strip()

    def test_parse_invoice_date_regex_fallback(self):
        """Test date extraction via regex path (non-ISO format)."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 15/03/2024\nBill From: Test Corp\nTotal: $100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        # Should normalize to ISO 8601
        assert ctx.data["parsed_invoice"]["date"] == "2024-03-15"

    def test_parse_invoice_dash_separated_dates_eu_order(self):
        """Test dash-separated dates use EU (day-first) ordering."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 01-02-2024\nBill From: Test Corp\nTotal: $100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        # EU order: 01-02-2024 → February 1, 2024
        assert ctx.data["parsed_invoice"]["date"] == "2024-02-01"

    def test_parse_invoice_brl_currency_detection(self):
        """Test Brazilian Real currency detection."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: R$100.00"
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert ctx.data["parsed_invoice"]["currency"] == "BRL"

    def test_parse_invoice_tab_separated_line_items(self):
        """Test that tab-separated line items are parsed correctly."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Item\tQty\tPrice\n"
            "Widget\t10\t$15.00\n"
            "Total: $150.00"
        )
        ctx = ProcessContext(
            transaction=Transaction(reference="test", skills=[]),
            data={"pdf_text": text},
        )
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = ctx.data["parsed_invoice"]["line_items"]
        assert len(items) == 1
        assert items[0]["description"] == "Widget"
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 15.00
