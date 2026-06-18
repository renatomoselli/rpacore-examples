"""Unit tests for deterministic sample repository setup."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from create_sample_repos import OLD_COMMIT_DATE, _git_stdout, _run_git, prepare_sample_repos


class TestCreateSampleRepos:
    def test_wraps_missing_git_as_system_exception(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(SystemException, match="git command not found"):
                _run_git(["init"])

    def test_git_stdout_returns_command_output(self, tmp_path):
        result = Mock(stdout="main\n")

        with patch("subprocess.run", return_value=result):
            assert _git_stdout(["branch", "--show-current"], cwd=tmp_path) == "main\n"

    @pytest.mark.parametrize(
        ("error", "message"),
        [
            (FileNotFoundError(), "git command not found"),
            (subprocess.TimeoutExpired(cmd=["git", "status"], timeout=30), "timed out"),
            (
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "status"],
                    stderr="fatal: not a git repository",
                ),
                "fatal: not a git repository",
            ),
        ],
    )
    def test_git_stdout_wraps_subprocess_errors(self, tmp_path, error, message):
        with patch("subprocess.run", side_effect=error):
            with pytest.raises(SystemException, match=message):
                _git_stdout(["status"], cwd=tmp_path)

    def test_prepare_sample_repos_creates_deterministic_structure(self, tmp_path):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            result = Mock()
            result.stdout = "master\n" if command[1:] == ["branch", "--show-current"] else ""
            return result

        with patch("subprocess.run", side_effect=fake_run):
            prepare_sample_repos(tmp_path / "sample_repos")

        alpha = tmp_path / "sample_repos" / "alpha"
        beta = tmp_path / "sample_repos" / "beta"

        assert (alpha / "README.md").read_text(encoding="utf-8") == "Hello World\n"
        assert (beta / "README.md").read_text(encoding="utf-8") == "Beta Project\n"
        assert (beta / "old_feature.txt").read_text(encoding="utf-8") == "Old feature\n"
        assert (beta / "uncommitted.txt").read_text(encoding="utf-8") == "Uncommitted\n"
        assert any(
            command[1:] == ["remote", "add", "origin", "https://github.com/example/alpha.git"]
            and kwargs["cwd"] == str(alpha)
            for command, kwargs in calls
        )
        assert any(
            command[1:] == ["checkout", "-b", "feature-old"]
            and kwargs["cwd"] == str(beta)
            for command, kwargs in calls
        )
        assert any(
            command[1:] == ["commit", "-m", "Old feature work"]
            and kwargs["cwd"] == str(beta)
            and kwargs["env"]["GIT_AUTHOR_DATE"] == OLD_COMMIT_DATE
            and kwargs["env"]["GIT_COMMITTER_DATE"] == OLD_COMMIT_DATE
            for command, kwargs in calls
        )
