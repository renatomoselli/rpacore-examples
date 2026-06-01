"""Unit tests for the CheckStaleBranches skill."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.check_stale_branches import CheckStaleBranches


class TestCheckStaleBranches:
    """Test the CheckStaleBranches skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}
        self.mock_ctx.config = {"stale_branch_days": 30}

    def test_detects_stale_branches(self):
        """Test that CheckStaleBranches correctly identifies stale branches."""
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  feature-old\n"
        mock_branch_result.returncode = 0

        # for-each-ref output: committerdate ISO format + branch name
        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00 master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.mock_ctx)

        assert "master" in self.mock_ctx.data["all_branches"]
        assert "feature-old" in self.mock_ctx.data["all_branches"]

    def test_skips_detached_head(self):
        """Test that CheckStaleBranches skips detached HEAD entries."""
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  (HEAD detached at abc123)\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00 master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.mock_ctx)

        assert "(HEAD detached at abc123)" not in self.mock_ctx.data["all_branches"]

    def test_skips_remote_tracking_branches(self):
        """Test that CheckStaleBranches skips remote-tracking branches."""
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  remotes/origin/feature-old\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00 master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.mock_ctx)

        assert "remotes/origin/feature-old" not in self.mock_ctx.data["all_branches"]

    def test_uses_config_threshold(self):
        """Test that CheckStaleBranches reads threshold from config."""
        self.mock_ctx.config = {"stale_branch_days": 60}

        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00 master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.mock_ctx)

        assert "master" in self.mock_ctx.data["all_branches"]

    def test_raises_on_missing_current_repo(self):
        """Test that CheckStaleBranches raises when current_repo is missing."""
        self.mock_ctx.data = {}
        skill = CheckStaleBranches("check_stale_branches", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_repo" in str(exc_info.value)

    def test_raises_on_git_not_found(self):
        """Test that CheckStaleBranches raises SystemException when git is not installed."""
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CheckStaleBranches("check_stale_branches", 4)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "git command not found" in str(exc_info.value)

    def test_raises_on_timeout(self):
        """Test that CheckStaleBranches raises SystemException on timeout."""
        import subprocess

        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CheckStaleBranches("check_stale_branches", 4)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "timed out" in str(exc_info.value)

    def test_raises_on_subprocess_error_for_each_ref(self):
        """Test that SubprocessError on for-each-ref raises SystemException."""
        import subprocess

        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        with patch("subprocess.run", side_effect=[
            mock_branch_result,
            subprocess.SubprocessError("for-each-ref failed"),
        ]):
            skill = CheckStaleBranches("check_stale_branches", 4)

            with pytest.raises(SystemException) as exc_info:
                skill.execute(self.mock_ctx)
            assert "git for-each-ref failed" in str(exc_info.value)
