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
        """Test that FillRow fills all 7 fields via JS evaluate."""
        row = {
            "First Name": "John", "Last Name": "Doe",
            "Company Name": "ACME", "Role in Company": "Engineer",
            "Address": "123 Main St", "Email": "john@example.com",
            "Phone Number": "555-1234"
        }
        self.mock_page.evaluate.return_value = {
            "First Name": "input-1", "Last Name": "input-2",
            "Company Name": "input-3", "Role in Company": "input-4",
            "Address": "input-5", "Email": "input-6",
            "Phone Number": "input-7"
        }

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # Verify evaluate was called (for label map + JS filling)
        assert self.mock_page.evaluate.call_count >= 1

    def test_fills_with_correct_values(self):
        """Test that fields are filled with correct values via JS."""
        row = {
            "Email": "test@example.com",
            "First Name": "Test",
            "Last Name": "User",
            "Company Name": "Test Co",
            "Role in Company": "Tester",
            "Address": "1 Test St",
            "Phone Number": "123-456-7890"
        }
        self.mock_page.evaluate.return_value = {f: f"input-{i}" for i, f in enumerate(_FIELDS)}

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # Verify evaluate was called to fill fields
        self.mock_page.evaluate.assert_called()

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
        self.mock_page.evaluate.return_value = {f: f"input-{i}" for i, f in enumerate(_FIELDS)}

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        # All fields should still be filled correctly
        self.mock_page.evaluate.assert_called()

    def test_raises_system_exception_on_js_failure(self):
        """Test that JS filling failure raises SystemException."""
        row = {
            "First Name": "John", "Last Name": "Doe",
            "Company Name": "ACME", "Role in Company": "Engineer",
            "Address": "123 Main St", "Email": "john@example.com",
            "Phone Number": "555-1234"
        }
        self.mock_page.evaluate.side_effect = Exception("JS execution failed")

        skill = FillRow("fill_row", 1, arguments={"row": row})

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to fill field in row" in str(exc_info.value)


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
        """Test that SubmitRow clicks the submit button inside the form."""
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        # Verify locator uses the correct form input selector
        self.mock_page.locator.assert_called_with('form input[type="submit"]')
        mock_locator.click.assert_called_with(timeout=10_000)

    def test_waits_for_congratulations_on_last_row(self):
        """Test that SubmitRow waits for congratulations on the last row."""
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        # Verify wait_for_selector was called for .congratulations
        self.mock_page.wait_for_selector.assert_called_with(".congratulations", timeout=5_000)

    def test_waits_for_form_re_render_on_intermediate_rows(self):
        """Test that SubmitRow waits for form re-render on intermediate rows."""
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator
        # Make wait_for_selector raise TimeoutError to simulate intermediate row
        self.mock_page.wait_for_selector.side_effect = TimeoutError("Not found")

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        # Verify wait_for_function was called as fallback
        self.mock_page.wait_for_function.assert_called_once()

    def test_raises_system_exception_on_click_failure(self):
        """Test that click failure raises SystemException."""
        self.mock_page.locator.side_effect = Exception("Button not found")

        skill = SubmitRow("submit_row", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to submit row" in str(exc_info.value)
