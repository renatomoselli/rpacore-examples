"""Unit tests for the CheckWorkingTree step."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from steps.check_working_tree import CheckWorkingTree
from tests.conftest import make_context


class TestCheckWorkingTree:
    """Test the CheckWorkingTree step."""

    def setup_method(self):
        self.ctx = make_context(state={"current_repo": "/tmp/test_repo"})

    def test_detects_uncommitted_changes(self):
        mock_result = Mock()
        mock_result.stdout = " M README.md\nA  src/main.py\n D docs/guide.md\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            step = CheckWorkingTree("check_working_tree", 1)
            step.execute(self.ctx)

        mock_run.assert_called_once_with(
            ["git", "-C", "/tmp/test_repo", "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
        assert self.ctx.state["uncommitted_changes"] == [
            "README.md", "src/main.py", "docs/guide.md",
        ]

    def test_detects_no_changes(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            step = CheckWorkingTree("check_working_tree", 1)
            step.execute(self.ctx)

        assert self.ctx.state["uncommitted_changes"] == []

    def test_preserves_leading_spaces_in_filename(self):
        mock_result = Mock()
        mock_result.stdout = " M   file_with_spaces\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            step = CheckWorkingTree("check_working_tree", 1)
            step.execute(self.ctx)

        assert self.ctx.state["uncommitted_changes"] == ["  file_with_spaces"]

    def test_reports_rename_target_filename(self):
        mock_result = Mock()
        mock_result.stdout = "R  old_name.txt -> new_name.txt\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            step = CheckWorkingTree("check_working_tree", 1)
            step.execute(self.ctx)

        assert self.ctx.state["uncommitted_changes"] == ["new_name.txt"]

    def test_reports_copy_target_filename(self):
        mock_result = Mock()
        mock_result.stdout = "C  source.txt -> copied.txt\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            step = CheckWorkingTree("check_working_tree", 1)
            step.execute(self.ctx)

        assert self.ctx.state["uncommitted_changes"] == ["copied.txt"]

    def test_raises_on_missing_current_repo(self):
        ctx = make_context()  # no state
        step = CheckWorkingTree("check_working_tree", 1)

        with pytest.raises(SystemException, match="Missing required state key: current_repo"):
            step.execute(ctx)

    def test_raises_on_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            step = CheckWorkingTree("check_working_tree", 1)
            with pytest.raises(SystemException, match="git command not found"):
                step.execute(self.ctx)

    def test_raises_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            step = CheckWorkingTree("check_working_tree", 1)
            with pytest.raises(SystemException, match="timed out"):
                step.execute(self.ctx)

    def test_raises_on_os_error(self):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            step = CheckWorkingTree("check_working_tree", 1)
            with pytest.raises(SystemException, match="git status failed"):
                step.execute(self.ctx)

    def test_raises_on_git_error(self):
        import subprocess
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not a git repository"

        with patch("subprocess.run", return_value=mock_result):
            step = CheckWorkingTree("check_working_tree", 1)
            with pytest.raises(SystemException, match="exit code 128"):
                step.execute(self.ctx)
