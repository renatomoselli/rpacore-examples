"""Unit tests for the CheckRemotes skill."""

from unittest.mock import Mock, patch

import pytest

from oref import SystemException
from skills.check_remotes import CheckRemotes


class TestCheckRemotes:
    """Test the CheckRemotes skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

    def test_parses_remote_output(self):
        """Test that CheckRemotes correctly parses git remote -v output."""
        mock_result = Mock()
        mock_result.stdout = (
            "origin\thttps://github.com/example/repo.git (fetch)\n"
            "origin\thttps://github.com/example/repo.git (push)\n"
            "upstream\thttps://github.com/upstream/repo.git (fetch)\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["remotes"] == {
            "origin": "https://github.com/example/repo.git",
            "upstream": "https://github.com/upstream/repo.git",
        }

    def test_returns_empty_dict_for_no_remotes(self):
        """Test that CheckRemotes returns empty dict when no remotes configured."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["remotes"] == {}

    def test_deduplicates_remote_urls(self):
        """Test that CheckRemotes keeps only the first URL for each remote name."""
        mock_result = Mock()
        mock_result.stdout = (
            "origin\thttps://github.com/example/repo.git (fetch)\n"
            "origin\thttps://github.com/other/repo.git (push)\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.mock_ctx)

        # First seen URL is kept
        assert self.mock_ctx.data["remotes"]["origin"] == "https://github.com/example/repo.git"

    def test_raises_on_missing_current_repo(self):
        """Test that CheckRemotes raises when current_repo is missing."""
        self.mock_ctx.data = {}
        skill = CheckRemotes("check_remotes", 3)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_repo" in str(exc_info.value)

    def test_raises_on_git_not_found(self):
        """Test that CheckRemotes raises SystemException when git is not installed."""
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CheckRemotes("check_remotes", 3)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "git command not found" in str(exc_info.value)

    def test_raises_on_timeout(self):
        """Test that CheckRemotes raises SystemException on timeout."""
        import subprocess

        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CheckRemotes("check_remotes", 3)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "timed out" in str(exc_info.value)
