"""Unit tests for ParseInvoice skill."""

from __future__ import annotations

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from skills.parse_invoice import ParseInvoice

class TestParseInvoice:
    """Tests for ParseInvoice skill."""

    def test_parse_invoice_field_extraction(self, sample_invoice_text: str):
        """Test extraction of all invoice fields."""
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = sample_invoice_text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        parsed = tx.state["parsed_invoice"]
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
            tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
            tx.state["pdf_text"] = text
            ctx = ProcessContext(transaction=tx, config={})
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert tx.state["parsed_invoice"]["date"] == expected_date, f"Failed for text: {text}"

    def test_parse_invoice_currency_detection_from_total(self):
        """Test currency detected from total string first."""
        texts = [
            ("Total: €100.00", "€"),
            ("Total: $50.00", "$"),
            ("Total: £75.00", "£"),
            ("Total: ¥1000", "¥"),
        ]
        for text, expected_currency in texts:
            tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
            tx.state["pdf_text"] = text
            ctx = ProcessContext(transaction=tx, config={})
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert tx.state["parsed_invoice"]["currency"] == expected_currency

    def test_parse_invoice_empty_text(self):
        """Test that empty text raises SystemException."""
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = ""
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)

        with pytest.raises(SystemException, match="No PDF text"):
            skill.execute(ctx)

    def test_parse_invoice_no_line_items(self):
        """Test parsing when no line items are present."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: $100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["line_items"] == []

    def test_parse_invoice_vendor_casing_preserved(self):
        """Test that vendor casing is preserved from PDF text."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Euro Parts GmbH\nTotal: $100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["vendor"] == "Euro Parts GmbH"

    def test_parse_invoice_sanitizes_durable_state_fields(self):
        """Control characters and oversized parsed fields are cleaned before persistence."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\x00\x01\n"
            "Date: 2024-01-15\n"
            f"Bill From: {'A' * 200}\u0085 Corp\n"
            "Widget 1 $10.00\n"
            "Total: $10.00"
        )
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        parsed = tx.state["parsed_invoice"]
        assert "\x00" not in parsed["invoice_number"]
        assert "\u0085" not in parsed["vendor"]
        assert len(parsed["vendor"]) == 120

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
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = tx.state["parsed_invoice"]["line_items"]
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
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = tx.state["parsed_invoice"]["line_items"]
        assert len(items) == 1
        assert "Adapter" in items[0]["description"]
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 15.00

    def test_parse_invoice_compact_tab_glyph_line_items(self):
        """Recover line items when PDF extraction turns tabs into literal n glyphs."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Widget An10n$15.00\n"
            "Widget Bn5n$20.00\n"
            "Total: $250.00"
        )
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = tx.state["parsed_invoice"]["line_items"]
        assert len(items) == 2
        assert items[0]["description"] == "Widget A"
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 15.00
        assert items[1]["description"] == "Widget B"

    def test_parse_invoice_compact_fallback_does_not_parse_words_with_n(self):
        """Words containing n should not be treated as compact separators."""
        text = (
            "INVOICE\n"
            "Invoice Number: INV-001\n"
            "Date: 2024-01-15\n"
            "Bill From: Test Corp\n"
            "Plan-n-Go 2$10.00\n"
            "Total: $20.00"
        )
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["line_items"] == []

    def test_parse_invoice_default_currency(self):
        """Test that currency defaults to USD when no symbol found."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: 100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["currency"] == "USD"

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
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["total"] == "$110.00"

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
            tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
            tx.state["pdf_text"] = text
            ctx = ProcessContext(transaction=tx, config={})
            skill = ParseInvoice(name="parse_invoice", execution_order=1)
            skill.execute(ctx)
            assert tx.state["parsed_invoice"]["invoice_number"] == label.split(":")[-1].strip()

    def test_parse_invoice_date_regex_fallback(self):
        """Test date extraction via regex path (non-ISO format)."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 15/03/2024\nBill From: Test Corp\nTotal: $100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["date"] == "2024-03-15"

    def test_parse_invoice_dash_separated_dates_eu_order(self):
        """Test dash-separated dates use EU (day-first) ordering."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 01-02-2024\nBill From: Test Corp\nTotal: $100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["date"] == "2024-02-01"

    def test_parse_invoice_brl_currency_detection(self):
        """Test Brazilian Real currency detection."""
        text = "INVOICE\nInvoice Number: INV-001\nDate: 2024-01-15\nBill From: Test Corp\nTotal: R$100.00"
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        assert tx.state["parsed_invoice"]["currency"] == "BRL"

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
        tx = Transaction(reference="test", skills=[ParseInvoice(name="parse_invoice", execution_order=1)])
        tx.state["pdf_text"] = text
        ctx = ProcessContext(transaction=tx, config={})
        skill = ParseInvoice(name="parse_invoice", execution_order=1)
        skill.execute(ctx)

        items = tx.state["parsed_invoice"]["line_items"]
        assert len(items) == 1
        assert items[0]["description"] == "Widget"
        assert items[0]["quantity"] == 10
        assert items[0]["unit_price"] == 15.00
