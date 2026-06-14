from __future__ import annotations

"""
Pytest fixtures for RPA Challenge tests.

This module provides common fixtures for both unit and integration tests.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock

import pytest

from rpacore import ProcessContext, Transaction
from skills._utils import find_row_value

# Add parent directory to path for importing skills
sys.path.insert(0, str(Path(__file__).parent.parent))


# Fixtures for unit tests (mock-based)
@pytest.fixture
def mock_page() -> Mock:
    """Create a mock Playwright page object."""
    mock_page = Mock()
    mock_page.get_by_role = Mock()
    mock_page.locator = Mock()
    mock_page.fill = Mock()
    mock_page.click = Mock()
    mock_page.is_visible = Mock(return_value=True)
    mock_page.is_enabled = Mock(return_value=True)
    return mock_page


@pytest.fixture
def mock_browser() -> Mock:
    """Create a mock Playwright browser object."""
    mock_browser = Mock()
    mock_browser.new_page = Mock(return_value=Mock())
    return mock_browser


@pytest.fixture
def mock_context() -> ProcessContext:
    """Create a mock ProcessContext with resources."""
    return ProcessContext(
        transaction=Mock(spec=Transaction, state={}),
        resources={"page": Mock(), "_pw": Mock()},
        config={},
    )


# Fixtures for integration tests
@pytest.fixture
def sample_excel_rows() -> list[Dict[str, str]]:
    """Sample data matching challenge schema for testing."""
    return [
        {
            "First Name": "John", "Last Name": "Doe",
            "Company Name": "ACME Corp", "Role in Company": "Software Engineer",
            "Address": "123 Main Street", "Email": "john.doe@example.com",
            "Phone Number": "555-0100"
        },
        {
            "First Name": "Jane", "Last Name": "Smith",
            "Company Name": "Tech Solutions", "Role in Company": "Product Manager",
            "Address": "456 Oak Avenue", "Email": "jane.smith@example.com",
            "Phone Number": "555-0200"
        },
        {
            "First Name": "Bob", "Last Name": "Johnson",
            "Company Name": "Global Industries", "Role in Company": "Analyst",
            "Address": "789 Pine Road", "Email": "bob.johnson@example.com",
            "Phone Number": "555-0300"
        }
    ]


@pytest.fixture
def empty_excel_rows() -> list[Dict[str, str]]:
    """Empty rows for testing error paths."""
    return []


@pytest.fixture
def minimal_excel_rows() -> list[Dict[str, str]]:
    """Rows with minimal data for testing boundary conditions."""
    return [
        {
            "First Name": "",  # Empty value
            "Last Name": "Doe",
            "Company Name": "Test Co",
            "Role in Company": "Tester",
            "Address": "1 Test St",
            "Email": "test@example.com",
            "Phone Number": "555-9999"
        }
    ]


@pytest.fixture
def incomplete_excel_rows() -> list[Dict[str, str]]:
    """Rows missing some required fields."""
    return [
        {
            "First Name": "Partial",
            # Missing: Last Name, Company Name, Role in Company, etc.
            "Email": "partial@example.com"
        }
    ]


# Helper functions
def get_field_value(row: Dict[str, Any], field: str) -> str:
    """Helper to look up field value case-insensitively."""
    return find_row_value(row, field)
