"""
Unit tests for row.py skills (FillRow, SubmitRow).

These tests use mocked browser objects to avoid requiring actual Playwright.
"""

import pytest
from unittest.mock import Mock, call, patch
from oref import ProcessContext, Transaction, SystemException, BusinessException

from skills.row import FillRow, SubmitRow, _FIELDS, _find_row_value


class TestFindRowValue:
    """Test the _find_row_value helper function."""

    def test_finds_exact_match(self):
        """Test finding a field with exact match."""
        row = {"First Name": "John"}
        result = _find_row_value(row, "First Name")
        assert result == "John"

    def test_finds_case_insensitive(self):
        """Test case-insensitive lookup."""
        row = {"first name": "john"}  # lowercase key
        result = _find_row_value(row, "First Name")
        assert result == "john"

    def test_handles_none_value(self):
        """Test handling None as value."""
        row = {"First Name": None}
        result = _find_row_value(row, "First Name")
        assert result == ""

    def test_returns_empty_when_not_found(self):
        """Test returning empty string when field not found."""
        row = {"Last Name": "Doe"}
        result = _find_row_value(row, "First Name")
        assert result == ""

    def test_handles_mixed_case_key(self):
        """Test handling mixed-case keys in row dict."""
        row = {"FIRST NAME": "JANE"}
        result = _find_row_value(row, "first name")
        assert result == "JANE"


class TestFillRow:
    """Test the FillRow skill with mocked browser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="fill-row")
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            data={"page": self.mock_page, "_pw": Mock()}
        )

    def test_fills_all_fields(self):
        """Test that FillRow fills all 7 fields."""
        row = {
            "First Name": "John", "Last Name": "Doe",
            "Company Name": "ACME", "Role in Company": "Engineer",
            "Address": "123 Main St", "Email": "john@example.com",
            "Phone Number": "555-1234"
        }

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # Verify all fields were filled
        for field in _FIELDS:
            assert self.mock_page.get_by_label(field).fill.called

    def test_fills_with_correct_values(self):
        """Test that fields are filled with correct values."""
        row = {
            "Email": "test@example.com",
            "First Name": "Test",
            "Last Name": "User",
            "Company Name": "Test Co",
            "Role in Company": "Tester",
            "Address": "1 Test St",
            "Phone Number": "123-456-7890"
        }

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # Verify each field was filled with its value
        for field in _FIELDS:
            value = row[field] if field in row else ""
            self.mock_page.get_by_label(field).fill.assert_any_call(value, timeout=10_000)

    def test_raises_business_exception_on_missing_fields(self):
        """Test that missing required fields raises BusinessException."""
        skill = FillRow("fill_row", 1, arguments={"row": {"First Name": "John"}})  # Only 1 of 7 fields

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "missing required fields" in str(exc_info.value)

    def test_raises_business_exception_for_empty_required_field(self):
        """Test that empty required field raises BusinessException."""
        row = {
            "First Name": "John",
            "Last Name": "",  # Empty string — FillRow rejects empty required fields
            "Company Name": "ACME",
            "Role in Company": "Engineer",
            "Address": "123 Main St",
            "Email": "john@example.com",
            "Phone Number": "555-1234"
        }

        skill = FillRow("fill_row", 1, arguments={"row": row})

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "missing required fields" in str(exc_info.value)
        assert "Last Name" in str(exc_info.value)

    def test_uses_case_insensitive_lookup(self):
        """Test that FillRow handles case-insensitive header lookup."""
        # Row with lowercase headers (as might come from some Excel configs)
        row = {
            "email": "john@example.com",
            "first name": "John",
            "last name": "Doe",
            "company name": "ACME",
            "role in company": "Engineer",
            "address": "123 Main St",
            "phone number": "555-1234"
        }

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # All fields should still be filled correctly
        for field in _FIELDS:
            assert self.mock_page.get_by_label(field).fill.called


class TestSubmitRow:
    """Test the SubmitRow skill with mocked browser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="submit-row")
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            data={"page": self.mock_page}
        )

    def test_submits_button(self):
        """Test that SubmitRow clicks the Submit button."""
        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.get_by_role.assert_called_with(
            "button",
            name="Submit"
        )
        self.mock_page.get_by_role("button", name="Submit").click.assert_called_with(timeout=10_000)

    def test_waits_after_submit(self):
        """Test that SubmitRow waits 500ms after submission."""
        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.wait_for_timeout.assert_called_with(500)

    def test_raises_system_exception_on_click_failure(self):
        """Test that click failure raises SystemException."""
        self.mock_page.get_by_role.side_effect = Exception("Button not found")

        skill = SubmitRow("submit_row", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to submit row" in str(exc_info.value)
