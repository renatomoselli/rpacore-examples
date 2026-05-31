"""Unit tests for the CheckWorkingTree skill."""

from unittest.mock import Mock, patch

import pytest

from oref import SystemException
from skills.check_working_tree import CheckWorkingTree


class TestCheckWorkingTree:
    """Test the CheckWorkingTree skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

    def test_detects_uncommitted_changes(self):
        """Test that CheckWorkingTree correctly parses git status --porcelain output."""
        mock_result = Mock()
        mock_result.stdout = " M README.md\nA src/main.py\n D docs/guide.md\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            skill = CheckWorkingTree("check_working_tree", 1)
            skill.execute(self.mock_ctx)

        mock_run.assert_called_once_with(
            ["git", "-C", "/tmp/test_repo", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert self.mock_ctx.data["uncommitted_changes"] == [
            "README.md",
            "src/main.py",
            "docs/guide.md",
        ]

    def test_detects_no_changes(self):
        """Test that CheckWorkingTree returns empty list when no changes."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckWorkingTree("check_working_tree", 1)
            skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["uncommitted_changes"] == []

    def test_strips_leading_spaces_after_prefix(self):
        """Test that CheckWorkingTree lstrip removes leading spaces after status prefix."""
        mock_result = Mock()
        # " M " prefix + filename with leading spaces (e.g. git rename format)
        mock_result.stdout = " M   file_with_spaces\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckWorkingTree("check_working_tree", 1)
            skill.execute(self.mock_ctx)

        # lstrip(" ") removes leading spaces after the 2-char status prefix
        assert self.mock_ctx.data["uncommitted_changes"] == ["file_with_spaces"]

    def test_raises_on_missing_current_repo(self):
        """Test that CheckWorkingTree raises when current_repo is missing."""
        self.mock_ctx.data = {}
        skill = CheckWorkingTree("check_working_tree", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_repo" in str(exc_info.value)

    def test_raises_on_git_not_found(self):
        """Test that CheckWorkingTree raises SystemException when git is not installed."""
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CheckWorkingTree("check_working_tree", 1)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "git command not found" in str(exc_info.value)

    def test_raises_on_timeout(self):
        """Test that CheckWorkingTree raises SystemException on timeout."""
        import subprocess

        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CheckWorkingTree("check_working_tree", 1)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "timed out" in str(exc_info.value)

    def test_raises_on_git_error(self):
        """Test that CheckWorkingTree raises SystemException on git error."""
        import subprocess

        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not a git repository"

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckWorkingTree("check_working_tree", 1)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "exit code 128" in str(exc_info.value)
