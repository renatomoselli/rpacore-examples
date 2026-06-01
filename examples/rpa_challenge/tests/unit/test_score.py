"""
Unit tests for score.py skill (RecordScore).

These tests use mocked browser objects.
"""

import pytest
from unittest.mock import Mock
from rpacore import ProcessContext, Transaction, SystemException

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
        self.mock_page.text_content.return_value = "success rate is 85%. Congratulations!"

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # Verify the correct API calls were made
        self.mock_page.wait_for_selector.assert_called_with(".congratulations", timeout=15_000)
        self.mock_page.text_content.assert_called_with("body")
        assert self.mock_ctx.data["score"] == "85%"

    def test_stores_score_in_ctx_data(self):
        """Test that score is stored in ctx.data."""
        self.mock_page.text_content.return_value = "success rate is 92%. Congratulations!"

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["score"] == "92%"

    def test_strips_whitespace_from_score(self):
        """Test that the regex extracts just the numeric score."""
        self.mock_page.text_content.return_value = "  success rate is 85%.  Congratulations!  "

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # re.search extracts the group, so whitespace around the match is irrelevant
        assert self.mock_ctx.data["score"] == "85%"

    def test_does_not_stop_browser(self):
        """Test that RecordScore no longer stops the browser (main.py owns lifecycle)."""
        self.mock_page.text_content.return_value = "success rate is 85%. Congratulations!"

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # Browser cleanup is owned by main.py — RecordScore should not pop/stop _pw
        self.mock_pw.stop.assert_not_called()
        assert "_pw" in self.mock_ctx.data

    def test_handles_wait_for_selector_timeout(self):
        """Test timeout when congratulations element not found."""
        self.mock_page.wait_for_selector.side_effect = Exception("Timeout")

        skill = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_handles_text_content_failure(self):
        """Test when body text cannot be read."""
        self.mock_page.wait_for_selector.return_value = None
        self.mock_page.text_content.side_effect = Exception("Body not found")

        skill = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_does_not_stop_browser_on_error(self):
        """Test that RecordScore does not stop browser even on error."""
        self.mock_page.text_content.side_effect = Exception("Content failed")

        skill = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)
        # Browser cleanup is owned by main.py
        self.mock_pw.stop.assert_not_called()

    def test_uses_correct_selector_and_api(self):
        """Test that the correct CSS selector and API are used."""
        self.mock_page.text_content.return_value = "success rate is 77%. Congratulations!"

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        # Verify wait_for_selector uses .congratulations
        self.mock_page.wait_for_selector.assert_called_with(".congratulations", timeout=15_000)
        # Verify text_content is called with "body"
        self.mock_page.text_content.assert_called_with("body")
        # Verify score was extracted correctly
        assert self.mock_ctx.data["score"] == "77%"

    def test_fallback_congratulations_message(self):
        """Test fallback when success rate regex doesn't match."""
        self.mock_page.text_content.return_value = "Congratulations! You have completed the challenge."

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["score"] == "Congratulations! You have completed the challenge."

    def test_fallback_returns_unknown_when_no_match(self):
        """Test fallback returns 'unknown' when neither regex matches."""
        self.mock_page.text_content.return_value = "Some random page text with no score."

        skill = RecordScore("record_score", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["score"] == "unknown"
