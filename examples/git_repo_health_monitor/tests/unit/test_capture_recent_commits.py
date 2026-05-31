"""Unit tests for the CaptureRecentCommits skill."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from oref import SystemException
from skills.capture_recent_commits import CaptureRecentCommits


class TestCaptureRecentCommits:
    """Test the CaptureRecentCommits skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

    def test_parses_git_log_output(self):
        """Test that CaptureRecentCommits correctly parses git log output."""
        mock_result = Mock()
        # Format: %H%x00%s%x00%ci
        mock_result.stdout = (
            "abc123\x00Initial commit\x002024-01-15T10:30:00-05:00\n"
            "def456\x00Add feature\x002024-01-14T08:00:00-05:00\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.mock_ctx)

        assert len(self.mock_ctx.data["recent_commits"]) == 2
        assert self.mock_ctx.data["recent_commits"][0]["commit_hash"] == "abc123"
        assert self.mock_ctx.data["recent_commits"][0]["subject"] == "Initial commit"
        assert "2024-01-15" in self.mock_ctx.data["recent_commits"][0]["timestamp"]

    def test_handles_pipe_in_subject(self):
        """Test that CaptureRecentCommits preserves pipe characters in subjects.

        split('\x00') on NUL-delimited output preserves the full subject,
        including any pipe characters within it.
        """
        mock_result = Mock()
        mock_result.stdout = "abc123\x00Feature | Add new endpoint\x002024-01-15T10:30:00-05:00\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.mock_ctx)

        assert len(self.mock_ctx.data["recent_commits"]) == 1
        assert self.mock_ctx.data["recent_commits"][0]["subject"] == "Feature | Add new endpoint"

    def test_handles_empty_log(self):
        """Test that CaptureRecentCommits returns empty list for empty log."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["recent_commits"] == []

    def test_sets_unknown_on_parse_failure(self):
        """Test that CaptureRecentCommits sets 'unknown' timestamp on parse failure."""
        mock_result = Mock()
        mock_result.stdout = "abc123\x00Bad date commit\x00not-a-date\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["recent_commits"][0]["timestamp"] == "unknown"

    def test_raises_on_missing_current_repo(self):
        """Test that CaptureRecentCommits raises when current_repo is missing."""
        self.mock_ctx.data = {}
        skill = CaptureRecentCommits("capture_recent_commits", 2)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_repo" in str(exc_info.value)

    def test_raises_on_git_not_found(self):
        """Test that CaptureRecentCommits raises SystemException when git is not installed."""
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CaptureRecentCommits("capture_recent_commits", 2)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "git command not found" in str(exc_info.value)

    def test_raises_on_timeout(self):
        """Test that CaptureRecentCommits raises SystemException on timeout."""
        import subprocess

        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CaptureRecentCommits("capture_recent_commits", 2)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "timed out" in str(exc_info.value)
