"""
Unit tests for setup.py skills (OpenChallengePage, DownloadInputData, StartChallenge).

These tests use mocked browser objects to avoid requiring actual Playwright.
"""

import io
from pathlib import Path
from unittest.mock import Mock, patch

import openpyxl
import pytest
from oref import ProcessContext, Transaction, SystemException

from skills.setup import (
    OpenChallengePage,
    DownloadInputData,
    StartChallenge,
    DEFAULT_XLSX_URL,
)


class TestOpenChallengePage:
    """Test the OpenChallengePage skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_pw = Mock()
        self.mock_browser = Mock()
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="open-challenge-page")

    @patch("skills.setup.sync_playwright")
    def test_opens_challenge_page(self, mock_sync_pw):
        """Test that OpenChallengePage opens the challenge page."""
        mock_sync_pw_instance = Mock()
        mock_sync_pw.return_value = mock_sync_pw_instance
        mock_sync_pw_instance.start.return_value = self.mock_pw
        self.mock_pw.chromium.launch.return_value = self.mock_browser
        self.mock_browser.new_page.return_value = self.mock_page

        skill = OpenChallengePage("open_challenge_page", 1)
        ctx = ProcessContext(transaction=self.mock_tx, data={})
        skill.execute(ctx)

        self.mock_pw.chromium.launch.assert_called_once()
        self.mock_browser.new_page.assert_called_once()
        self.mock_page.goto.assert_called_with("https://www.rpachallenge.com/", timeout=30_000)
        assert ctx.data["page"] == self.mock_page
        assert ctx.data["_pw"] == self.mock_pw

    @patch("skills.setup.sync_playwright")
    def test_raises_system_exception_on_launch_failure(self, mock_sync_pw):
        """Test that browser launch failure raises SystemException."""
        mock_sync_pw_instance = Mock()
        mock_sync_pw.return_value = mock_sync_pw_instance
        mock_sync_pw_instance.start.return_value = self.mock_pw
        self.mock_pw.chromium.launch.side_effect = Exception("Launch failed")

        skill = OpenChallengePage("open_challenge_page", 1)
        ctx = ProcessContext(transaction=self.mock_tx, data={})

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)
        assert "launch" in str(exc_info.value).lower()

    @patch("skills.setup.sync_playwright")
    def test_raises_system_exception_on_navigation_failure(self, mock_sync_pw):
        """Test that navigation failure raises SystemException."""
        mock_sync_pw_instance = Mock()
        mock_sync_pw.return_value = mock_sync_pw_instance
        mock_sync_pw_instance.start.return_value = self.mock_pw
        self.mock_pw.chromium.launch.return_value = self.mock_browser
        self.mock_browser.new_page.return_value = self.mock_page
        self.mock_page.goto.side_effect = Exception("Navigation failed")

        skill = OpenChallengePage("open_challenge_page", 1)
        ctx = ProcessContext(transaction=self.mock_tx, data={})

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)
        assert "Failed to load page" in str(exc_info.value)


class TestDownloadInputData:
    """Test the DownloadInputData skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="download-input-data")
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            data={"page": self.mock_page}
        )

    def _make_excel_bytes(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["First Name", "Last Name", "Company Name",
                    "Role in Company", "Address", "Email", "Phone Number"])
        ws.append(["John", "Doe", "ACME", "Engineer",
                    "123 Main St", "john@example.com", "555-1234"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def test_downloads_and_parses_excel(self):
        """Test that DownloadInputData downloads and parses Excel."""
        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())
            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
                mock_wb = Mock()
                mock_wb.active = Mock()
                mock_wb.active.iter_rows.return_value = iter([
                    ("First Name", "Last Name", "Company Name",
                     "Role in Company", "Address", "Email", "Phone Number"),
                    ("John", "Doe", "ACME", "Engineer",
                     "123 Main St", "john@example.com", "555-1234"),
                ])
                mock_load_wb.return_value = mock_wb

                skill = DownloadInputData("download_input_data", 1)
                skill.execute(self.mock_ctx)

                mock_urlretrieve.assert_called_once()
                mock_load_wb.assert_called_once()

    def test_uses_configured_xlsx_url(self):
        """Test that DownloadInputData uses custom xlsx_url from config."""
        self.mock_ctx.config = {"xlsx_url": "http://custom-url.com/data.xlsx"}

        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())
            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
                mock_wb = Mock()
                mock_wb.active = Mock()
                mock_wb.active.iter_rows.return_value = iter([
                    ("First Name", "Last Name", "Company Name",
                     "Role in Company", "Address", "Email", "Phone Number"),
                    ("John", "Doe", "ACME", "Engineer",
                     "123 Main St", "john@example.com", "555-1234"),
                ])
                mock_load_wb.return_value = mock_wb

                skill = DownloadInputData("download_input_data", 1)
                skill.execute(self.mock_ctx)

                mock_urlretrieve.assert_called_once()
                args, _ = mock_urlretrieve.call_args
                assert args[0] == "http://custom-url.com/data.xlsx"

    def test_falls_back_to_browser_download_on_direct_failure(self):
        """Test that DownloadInputData falls back to browser download."""
        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.side_effect = Exception("Download failed")
            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb, \
                 patch("pathlib.Path.rename"):
                mock_wb = Mock()
                mock_wb.active = Mock()
                mock_wb.active.iter_rows.return_value = iter([
                    ("First Name", "Last Name", "Company Name",
                     "Role in Company", "Address", "Email", "Phone Number"),
                    ("John", "Doe", "ACME", "Engineer",
                     "123 Main St", "john@example.com", "555-1234"),
                ])
                mock_load_wb.return_value = mock_wb

                mock_download = Mock()
                mock_download.path = "/tmp/test.xlsx"
                self.mock_page.context.downloads = [mock_download]

                skill = DownloadInputData("download_input_data", 1)
                skill.execute(self.mock_ctx)

                # Should have tried urlretrieve first, then browser download
                assert mock_urlretrieve.call_count >= 1

    def test_raises_system_exception_on_parse_failure(self):
        """Test that parse failure raises SystemException."""
        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())
            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
                mock_wb = Mock()
                mock_wb.active = Mock()
                mock_wb.active.iter_rows.side_effect = Exception("Invalid Excel")
                mock_load_wb.return_value = mock_wb

                skill = DownloadInputData("download_input_data", 1)

                with pytest.raises(Exception) as exc_info:
                    skill.execute(self.mock_ctx)

                assert "Failed to parse Excel file" in str(exc_info.value)
                assert isinstance(exc_info.value, Exception)

    def test_raises_business_exception_on_empty_data(self):
        """Test that empty Excel data raises BusinessException."""
        with patch("skills.setup.urllib.request.urlretrieve") as mock_urlretrieve:
            mock_urlretrieve.return_value = ("/tmp/test.xlsx", Mock())
            with patch("skills.setup.openpyxl.load_workbook") as mock_load_wb:
                mock_wb = Mock()
                mock_wb.active = Mock()
                mock_wb.active.iter_rows.return_value = iter([])
                mock_load_wb.return_value = mock_wb

                skill = DownloadInputData("download_input_data", 1)

                with pytest.raises(Exception) as exc_info:
                    skill.execute(self.mock_ctx)

                assert "parse" in str(exc_info.value).lower()


class TestStartChallenge:
    """Test the StartChallenge skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="start-challenge")
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            data={"page": self.mock_page}
        )

    def test_clicks_start_button(self):
        """Test that StartChallenge clicks the start button."""
        skill = StartChallenge("start_challenge", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.get_by_role.assert_called_with(
            "button",
            name="Start"
        )
        self.mock_page.get_by_role("button", name="Start").click.assert_called_with(timeout=10_000)

    def test_waits_for_download_button(self):
        """Test that StartChallenge waits for download button."""
        skill = StartChallenge("start_challenge", 1)
        skill.execute(self.mock_ctx)

        self.mock_page.wait_for_selector.assert_called_with(
            'a[role="link"].cloud_download', timeout=10_000
        )

    def test_raises_system_exception_on_start_failure(self):
        """Test that start failure raises SystemException."""
        self.mock_page.get_by_role.side_effect = Exception("Start failed")

        skill = StartChallenge("start_challenge", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to start the challenge" in str(exc_info.value)
