"""Unit tests for the CaptureRecentCommits skill."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.capture_recent_commits import CaptureRecentCommits
from tests.conftest import make_context


class TestCaptureRecentCommits:
    """Test the CaptureRecentCommits skill."""

    def setup_method(self):
        self.ctx = make_context(state={"current_repo": "/tmp/test_repo"})

    def test_parses_git_log_output(self):
        mock_result = Mock()
        mock_result.stdout = (
            "abc123\x00Initial commit\x002024-01-15T10:30:00-05:00\n"
            "def456\x00Add feature\x002024-01-14T08:00:00-05:00\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.ctx)

        assert len(self.ctx.state["recent_commits"]) == 2
        assert self.ctx.state["recent_commits"][0]["commit_hash"] == "abc123"
        assert self.ctx.state["recent_commits"][0]["subject"] == "Initial commit"
        assert "2024-01-15" in self.ctx.state["recent_commits"][0]["timestamp"]

    def test_handles_pipe_in_subject(self):
        mock_result = Mock()
        mock_result.stdout = "abc123\x00Feature | Add new endpoint\x002024-01-15T10:30:00-05:00\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.ctx)

        assert len(self.ctx.state["recent_commits"]) == 1
        assert self.ctx.state["recent_commits"][0]["subject"] == "Feature | Add new endpoint"

    def test_handles_empty_log(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.ctx)

        assert self.ctx.state["recent_commits"] == []

    def test_sets_unknown_on_parse_failure(self):
        mock_result = Mock()
        mock_result.stdout = "abc123\x00Bad date commit\x00not-a-date\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            skill.execute(self.ctx)

        assert self.ctx.state["recent_commits"][0]["timestamp"] == "unknown"

    def test_raises_on_missing_current_repo(self):
        ctx = make_context()
        skill = CaptureRecentCommits("capture_recent_commits", 2)
        with pytest.raises(SystemException, match="current_repo"):
            skill.execute(ctx)

    def test_raises_on_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            with pytest.raises(SystemException, match="git command not found"):
                skill.execute(self.ctx)

    def test_raises_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CaptureRecentCommits("capture_recent_commits", 2)
            with pytest.raises(SystemException, match="timed out"):
                skill.execute(self.ctx)
