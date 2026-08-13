from __future__ import annotations

"""
Unit tests for score.py step (RecordScore).

These tests use mocked browser objects.
"""

import pytest
from unittest.mock import Mock
from rpacore import ProcessContext, Transaction, SystemException

from steps.score import RecordScore
from steps._utils import DEFAULT_TIMEOUTS

pytestmark = pytest.mark.unit


class TestRecordScore:
    """Test the RecordScore step with mocked browser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = Mock()
        self.mock_pw = Mock()
        self.mock_tx = Mock(spec=Transaction, reference="record-score", state={})
        self.mock_ctx = ProcessContext(
            transaction=self.mock_tx,
            resources={"page": self.mock_page, "_pw": self.mock_pw},
            config={},
        )

    def test_reads_score_text(self):
        """Test that RecordScore reads the final score."""
        self.mock_page.text_content.return_value = "success rate is 85%. Congratulations!"

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        self.mock_page.wait_for_selector.assert_called_with(
            ".congratulations",
            timeout=DEFAULT_TIMEOUTS["score_extraction"],
        )
        self.mock_page.text_content.assert_called_with("body")
        assert self.mock_ctx.state["score"] == "85%"

    def test_stores_score_in_ctx_state(self):
        """Test that score is stored in ctx.state."""
        self.mock_page.text_content.return_value = "success rate is 92%. Congratulations!"

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        assert self.mock_ctx.state["score"] == "92%"

    def test_strips_whitespace_from_score(self):
        """Test that the regex extracts just the numeric score."""
        self.mock_page.text_content.return_value = "  success rate is 85%.  Congratulations!  "

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        assert self.mock_ctx.state["score"] == "85%"

    def test_reads_score_without_percent_sign(self):
        """Test that minor score text format changes still parse."""
        self.mock_page.text_content.return_value = "success rate is 85. Congratulations!"

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        assert self.mock_ctx.state["score"] == "85%"

    def test_does_not_stop_browser(self):
        """Test that RecordScore no longer stops the browser (main.py owns lifecycle)."""
        self.mock_page.text_content.return_value = "success rate is 85%. Congratulations!"

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        self.mock_pw.stop.assert_not_called()
        assert "_pw" in self.mock_ctx.resources

    def test_handles_wait_for_selector_timeout(self):
        """Test timeout when congratulations element not found."""
        self.mock_page.wait_for_selector.side_effect = Exception("Timeout")

        step = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_handles_text_content_failure(self):
        """Test when body text cannot be read."""
        self.mock_page.wait_for_selector.return_value = None
        self.mock_page.text_content.side_effect = Exception("Body not found")

        step = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)

    def test_does_not_stop_browser_on_error(self):
        """Test that RecordScore does not stop browser even on error."""
        self.mock_page.text_content.side_effect = Exception("Content failed")

        step = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)
        self.mock_pw.stop.assert_not_called()

    def test_uses_correct_selector_and_api(self):
        """Test that the correct CSS selector and API are used."""
        self.mock_page.text_content.return_value = "success rate is 77%. Congratulations!"

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        self.mock_page.wait_for_selector.assert_called_with(
            ".congratulations",
            timeout=DEFAULT_TIMEOUTS["score_extraction"],
        )
        self.mock_page.text_content.assert_called_with("body")
        assert self.mock_ctx.state["score"] == "77%"

    def test_fallback_congratulations_message(self):
        """Test fallback extracts a percentage from alternate congratulations text."""
        self.mock_page.text_content.return_value = "Congratulations! You scored 85%. Great job."

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        self.mock_page.wait_for_selector.assert_called_with(
            ".congratulations",
            timeout=DEFAULT_TIMEOUTS["score_extraction"],
        )
        assert self.mock_ctx.state["score"] == "85%"

    def test_fallback_congratulations_message_without_percent_sign(self):
        self.mock_page.text_content.return_value = "Congratulations! You scored 85. Great job."

        step = RecordScore("record_score", 1)
        step.execute(self.mock_ctx)

        assert self.mock_ctx.state["score"] == "85%"

    def test_raises_when_congratulations_has_no_score(self):
        self.mock_page.text_content.return_value = "Congratulations! You have completed the challenge."

        step = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)
        assert "score" not in self.mock_ctx.state

    def test_raises_when_no_score_or_congratulations_match(self):
        """Test that unparseable final page text fails loudly."""
        self.mock_page.text_content.return_value = "Some random page text with no score."

        step = RecordScore("record_score", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.mock_ctx)

        assert "Failed to read final score" in str(exc_info.value)
        assert "score" not in self.mock_ctx.state
