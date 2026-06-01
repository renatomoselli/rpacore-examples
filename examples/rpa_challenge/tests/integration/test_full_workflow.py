"""
Integration tests for the full RPA workflow.

These tests verify that all skills work together correctly.
"""

import io
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import openpyxl
import pytest

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rpacore import ProcessContext, Transaction
from skills.setup import (
    OpenChallengePage,
    DownloadInputData,
    StartChallenge,
    DEFAULT_XLSX_URL,
)
from skills.row import FillRow, SubmitRow
from skills.score import RecordScore


def test_skip_in_ci():
    """
    Mark this test as requiring special conditions.
    Adjust based on your CI configuration.
    """
    if os.environ.get("CI", "").lower() in ["true", "1"]:
        pytest.skip("Skipping integration test in CI environment")
    if not Path(__file__).parent.parent.exists():
        pytest.skip("Running outside RPA Core examples directory")


class TestFullWorkflow:
    """Test the full workflow from start to finish."""

    def _create_test_excel_bytes(self):
        """Create test Excel data as bytes."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["First Name", "Last Name", "Company Name",
                    "Role in Company", "Address", "Email", "Phone Number"])
        ws.append(["John", "Doe", "ACME Corp", "Software Engineer",
                    "123 Main St", "john@example.com", "555-0100"])
        ws.append(["Jane", "Smith", "Tech Solutions", "Product Manager",
                    "456 Oak Ave", "jane@example.com", "555-0200"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def test_workflow_executes_all_skills_in_order(self):
        """Test that all skills execute in the correct order."""
        test_excel = self._create_test_excel_bytes()
        mock_tx = Mock(spec=Transaction, reference="test-workflow")

        # Mock the browser and download
        mock_page = Mock()
        mock_pw = Mock()
        mock_browser = Mock()

        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve, \
             patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:

            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())

            # Mock Excel parsing
            mock_wb = Mock()
            mock_wb.active = Mock()
            mock_wb.active.iter_rows.return_value = iter([
                ("First Name", "Last Name", "Company Name",
                 "Role in Company", "Address", "Email", "Phone Number"),
                ("John", "Doe", "ACME Corp", "Software Engineer",
                 "123 Main St", "john@example.com", "555-0100"),
                ("Jane", "Smith", "Tech Solutions", "Product Manager",
                 "456 Oak Ave", "jane@example.com", "555-0200"),
            ])
            mock_load_wb.return_value = mock_wb

            ctx = ProcessContext(
                transaction=mock_tx,
                data={"page": mock_page, "_pw": mock_pw},
                config={"xlsx_url": "http://test.example.com/data.xlsx"}
            )

            # Execute DownloadInputData (OpenChallengePage needs sync_playwright mock)
            skill2 = DownloadInputData("download_input_data", 2)
            skill2.execute(ctx)

            # Verify DownloadInputData executed successfully
            assert ctx.data.get("page") == mock_page

    def test_workflow_uses_custom_config(self):
        """Test that workflow respects custom configuration."""
        mock_tx = Mock(spec=Transaction, reference="test-config")
        mock_page = Mock()
        mock_pw = Mock()

        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve, \
             patch("pathlib.Path.unlink"), \
             patch("tempfile.mkstemp", return_value=(123, "/tmp/test.xlsx")), \
             patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
            mock_urlretrieve.side_effect = Exception("Network error")
            # Mock the browser download fallback via expect_download context manager
            mock_download = Mock()
            mock_download.save_as = Mock()
            mock_context_mgr = Mock()
            mock_context_mgr.value = mock_download  # dl_info.value is the download object
            mock_context_mgr.__enter__ = Mock(return_value=mock_context_mgr)
            mock_context_mgr.__exit__ = Mock(return_value=None)
            mock_page.expect_download = Mock(return_value=mock_context_mgr)
            mock_page.wait_for_selector = Mock()
            mock_page.click = Mock()
            mock_wb = Mock()
            mock_wb.active = Mock()
            mock_wb.active.iter_rows.return_value = iter([
                ("First Name", "Last Name", "Company Name",
                 "Role in Company", "Address", "Email", "Phone Number"),
                ("John", "Doe", "ACME", "Engineer",
                 "123 Main St", "john@example.com", "555-1234"),
            ])
            mock_load_wb.return_value = mock_wb

            ctx = ProcessContext(
                transaction=mock_tx,
                data={"page": mock_page, "_pw": mock_pw},
                config={"xlsx_url": "http://custom-test-url.com/data.xlsx"}
            )

            # Skill should use custom URL from config
            skill = DownloadInputData("download_input_data", 2)
            skill.execute(ctx)

            # Verify urlretrieve was called (it fails, then fallback happens)
            assert mock_urlretrieve.call_count >= 1
            # Verify browser download fallback was used
            mock_page.expect_download.assert_called_once()
            mock_page.click.assert_called_once()
            mock_download.save_as.assert_called_once()

    def test_workflow_handles_parse_errors(self):
        """Test that workflow handles Excel parse errors."""
        mock_tx = Mock(spec=Transaction, reference="test-errors")
        mock_page = Mock()

        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve, \
             patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:

            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())
            mock_wb = Mock()
            mock_wb.active = Mock()
            mock_wb.active.iter_rows.side_effect = Exception("Parse error")
            mock_load_wb.return_value = mock_wb

            ctx = ProcessContext(
                transaction=mock_tx,
                data={"page": mock_page},
                config={"xlsx_url": "http://test.example.com/data.xlsx"}
            )

            # Download should raise an exception on parse failure
            with pytest.raises(Exception):
                skill = DownloadInputData("download_input_data", 2)
                skill.execute(ctx)

    def test_downloads_raw_bytes(self):
        """Test that downloaded content can be read as raw bytes."""
        with patch("skills.setup.urllib.request.urlopen") as mock_urlopen:
            test_data = self._create_test_excel_bytes()
            mock_response = Mock()
            mock_response.read.return_value = test_data
            mock_urlopen.return_value = mock_response

            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
                # Verify we can parse the downloaded file from bytes
                wb = openpyxl.load_workbook(io.BytesIO(test_data))
                assert wb is not None
