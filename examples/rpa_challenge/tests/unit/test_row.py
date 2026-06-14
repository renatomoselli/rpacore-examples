from __future__ import annotations

"""
Unit tests for row.py skills (FillRow, SubmitRow).

These tests use mocked browser objects to avoid requiring actual Playwright.
"""

import pytest
from unittest.mock import Mock, call, patch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from rpacore import ProcessContext, Transaction, SystemException, BusinessException

from skills.row import FillRow, SubmitRow, _FIELDS
from skills._utils import (
    DEFAULT_TIMEOUTS,
    find_row_value as _find_row_value,
    get_timeout,
    missing_required_fields,
)

pytestmark = pytest.mark.unit

DEFAULT_CONFIG = {f"timeout_{key}": value for key, value in DEFAULT_TIMEOUTS.items()}


class TestFindRowValue:
    """Test the _find_row_value helper function."""

    def test_finds_exact_match(self):
        row = {"First Name": "John"}
        result = _find_row_value(row, "First Name")
        assert result == "John"

    def test_finds_case_insensitive(self):
        row = {"first name": "john"}
        result = _find_row_value(row, "First Name")
        assert result == "john"

    def test_handles_none_value(self):
        row = {"First Name": None}
        result = _find_row_value(row, "First Name")
        assert result == ""

    def test_preserves_numeric_zero_value(self):
        row = {"Phone Number": 0}
        result = _find_row_value(row, "Phone Number")
        assert result == "0"

    def test_returns_empty_when_not_found(self):
        row = {"Last Name": "Doe"}
        result = _find_row_value(row, "First Name")
        assert result == ""

    def test_handles_mixed_case_key(self):
        row = {"FIRST NAME": "JANE"}
        result = _find_row_value(row, "first name")
        assert result == "JANE"


class TestMissingRequiredFields:
    def test_uses_default_required_fields(self):
        row = {
            "First Name": "Jane",
            "Last Name": "Doe",
            "Company Name": "ACME",
            "Role in Company": "Engineer",
            "Address": "1 Test St",
            "Email": "",
            "Phone Number": "555-0100",
        }

        assert missing_required_fields(row) == ["Email"]

    def test_accepts_custom_field_list(self):
        row = {"Email": "jane@example.com", "Phone Number": ""}

        assert missing_required_fields(row, fields=["Email", "Phone Number"]) == ["Phone Number"]


class TestGetTimeout:
    def test_uses_config_override(self):
        assert get_timeout({"timeout_click": 1234}, "click") == 1234

    def test_raises_clear_error_for_unknown_timeout_key(self):
        with pytest.raises(KeyError) as exc_info:
            get_timeout({}, "not_a_timeout")

        assert "Unknown timeout key" in str(exc_info.value)

    def test_raises_clear_error_for_invalid_timeout_value(self):
        with pytest.raises(SystemException) as exc_info:
            get_timeout({"timeout_click": "fast"}, "click")

        assert "timeout_click" in str(exc_info.value)


class TestFillRow:
    """Test the FillRow skill with mocked browser."""

    def setup_method(self):
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="fill-row", state={})
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            resources={"page": self.mock_page, "_pw": Mock()},
            config=DEFAULT_CONFIG,
        )

    def test_fills_all_fields(self):
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

        assert self.mock_page.evaluate.call_count >= 1

    def test_fills_with_correct_values(self):
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

        self.mock_page.evaluate.assert_called()

    def test_fills_values_containing_percent_sign(self):
        row = {
            "Email": "test@example.com",
            "First Name": "Test",
            "Last Name": "User",
            "Company Name": "100% Quality Co",
            "Role in Company": "Tester",
            "Address": "1 Test St",
            "Phone Number": "123-456-7890"
        }
        self.mock_page.evaluate.return_value = {f: f"input-{i}" for i, f in enumerate(_FIELDS)}

        skill = FillRow("fill_row", 1, arguments={"row": row})
        skill.execute(self.mock_ctx)

        js_code = self.mock_page.evaluate.call_args.args[0]
        assert "100% Quality Co" in js_code

    def test_raises_business_exception_on_missing_fields(self):
        skill = FillRow("fill_row", 1, arguments={"row": {"First Name": "John"}})

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "missing required fields" in str(exc_info.value)
        assert "row_validation_failed" not in self.mock_ctx.state

    def test_raises_business_exception_for_empty_required_field(self):
        row = {
            "First Name": "John",
            "Last Name": "",
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

        self.mock_page.evaluate.assert_called()

    def test_raises_system_exception_on_js_failure(self):
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
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="submit-row", state={})
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            resources={"page": self.mock_page},
            config=DEFAULT_CONFIG,
        )

    def test_submits_button(self):
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.locator.assert_called_with('form input[type="submit"]')
        mock_locator.click.assert_called_with(timeout=DEFAULT_TIMEOUTS["click"])

    def test_waits_for_congratulations_on_last_row(self):
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.wait_for_selector.assert_called_with(".congratulations", timeout=DEFAULT_TIMEOUTS["congratulations_check"])

    def test_waits_for_form_re_render_on_intermediate_rows(self):
        mock_locator = Mock()
        self.mock_page.locator.return_value = mock_locator
        self.mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Not found")

        skill = SubmitRow("submit_row", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.wait_for_function.assert_called_once()

    def test_raises_system_exception_on_click_failure(self):
        self.mock_page.locator.side_effect = Exception("Button not found")

        skill = SubmitRow("submit_row", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to submit row" in str(exc_info.value)
