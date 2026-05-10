"""
Unit tests for score.py skill (RecordScore).

These tests use mocked browser objects.
"""

import pytest
from unittest.mock import Mock
from oref import ProcessContext, Transaction, SystemException

from skills.score import RecordScore


class TestRecordScore:
    """Test the RecordScore skill with mocked browser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_pw = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="record-score")
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            data={"page": self.mock_page, "_pw": self.mock_pw}
        )

    def test_reads_score_text(self):
        """Test that RecordScore reads the final score."""
        mock_locator = Mock()
        mock_locator.inner_text.return_value = "Your Score: 85%"
        self.mock_page.locator.return_value = mock_locator

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # Verify locator was used
        self.mock_page.locator.assert_called_with(".message2")
        mock_locator.wait_for.assert_called_with(timeout=10_000)
        mock_locator.inner_text.assert_called_once()

    def test_stores_score_in_ctx_data(self):
        """Test that score is stored in ctx.data."""
        mock_locator = Mock()
        mock_locator.inner_text.return_value = "Your Score: 92%"
        self.mock_page.locator.return_value = mock_locator

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["score"] == "Your Score: 92%"

    def test_strips_whitespace_from_score(self):
        """Test that leading/trailing whitespace is stripped."""
        mock_locator = Mock()
        mock_locator.inner_text.return_value = "   Your Score: 85%   "
        self.mock_page.locator.return_value = mock_locator

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["score"] == "Your Score: 85%"

    def test_stops_browser_in_finally_block(self):
        """Test that browser is stopped even if error occurs."""
        self.mock_page.locator.side_effect = Exception("Locator failed")

        skill = RecordScore("record_score", 1)

        with pytest.raises(Exception):
            skill.execute(self.mock_ctx)

        # Verify browser was stopped in finally block
        self.mock_pw.stop.assert_called_once()

    def test_handles_locator_wait_timeout(self):
        """Test timeout when score element not found."""
        self.mock_page.locator.return_value.wait_for.side_effect = Exception("Timeout")

        skill = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_handles_locator_not_found(self):
        """Test when score element cannot be found."""
        self.mock_page.locator.side_effect = Exception("Element not found")

        skill = RecordScore("record_score", 1)

        with pytest.raises(Exception) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_stops_browser_even_on_locator_error(self):
        """Test browser is stopped even when locator fails."""
        self.mock_page.locator.side_effect = Exception("Locator failed")

        skill = RecordScore("record_score", 1)

        with pytest.raises(Exception):
            skill.execute(self.mock_ctx)

        # Verify browser was still stopped
        self.mock_pw.stop.assert_called_once()

    def test_uses_correct_locator_selector(self):
        """Test that the correct CSS selector is used."""
        mock_locator = Mock()
        mock_locator.inner_text.return_value = "   Your Score: 85%   "
        self.mock_page.locator.return_value = mock_locator

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # Verify locator uses .message2 selector
        self.mock_page.locator.assert_called_with(".message2")
        # Verify score was stored correctly (stripped)
        assert self.mock_ctx.data["score"] == "Your Score: 85%"
