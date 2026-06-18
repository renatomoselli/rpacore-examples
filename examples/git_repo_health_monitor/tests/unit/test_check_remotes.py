"""Unit tests for the CheckRemotes skill."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.check_remotes import CheckRemotes
from tests.conftest import make_context


class TestCheckRemotes:
    """Test the CheckRemotes skill."""

    def setup_method(self):
        self.ctx = make_context(state={"current_repo": "/tmp/test_repo"})

    def test_parses_remote_output(self):
        mock_result = Mock()
        mock_result.stdout = (
            "origin\thttps://github.com/example/repo.git (fetch)\n"
            "origin\thttps://github.com/example/repo.git (push)\n"
            "upstream\thttps://github.com/upstream/repo.git (fetch)\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.ctx)

        assert self.ctx.state["remotes"] == {
            "origin": "https://github.com/example/repo.git",
            "upstream": "https://github.com/upstream/repo.git",
        }

    def test_returns_empty_dict_for_no_remotes(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.ctx)

        assert self.ctx.state["remotes"] == {}

    def test_deduplicates_remote_urls(self):
        mock_result = Mock()
        mock_result.stdout = (
            "origin\thttps://github.com/example/repo.git (fetch)\n"
            "origin\thttps://github.com/other/repo.git (push)\n"
        )
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            skill.execute(self.ctx)

        assert self.ctx.state["remotes"]["origin"] == "https://github.com/example/repo.git"

    def test_raises_on_missing_current_repo(self):
        ctx = make_context()
        skill = CheckRemotes("check_remotes", 3)
        with pytest.raises(SystemException, match="current_repo"):
            skill.execute(ctx)

    def test_raises_on_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CheckRemotes("check_remotes", 3)
            with pytest.raises(SystemException, match="git command not found"):
                skill.execute(self.ctx)

    def test_raises_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CheckRemotes("check_remotes", 3)
            with pytest.raises(SystemException, match="timed out"):
                skill.execute(self.ctx)

    def test_raises_on_os_error(self):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            skill = CheckRemotes("check_remotes", 3)
            with pytest.raises(SystemException, match="git remote failed"):
                skill.execute(self.ctx)

    def test_raises_on_nonzero_git_exit(self):
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not a git repository"

        with patch("subprocess.run", return_value=mock_result):
            skill = CheckRemotes("check_remotes", 3)
            with pytest.raises(SystemException, match="git remote returned exit code 128"):
                skill.execute(self.ctx)
