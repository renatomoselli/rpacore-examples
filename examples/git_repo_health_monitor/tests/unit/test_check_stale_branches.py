"""Unit tests for the CheckStaleBranches skill."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.check_stale_branches import CheckStaleBranches
from tests.conftest import make_context


class TestCheckStaleBranches:
    """Test the CheckStaleBranches skill."""

    def setup_method(self):
        self.ctx = make_context(
            state={"current_repo": "/tmp/test_repo"},
            config={"stale_branch_days": 30},
        )

    def test_detects_stale_branches(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  feature-old\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert "master" in self.ctx.state["all_branches"]
        assert "feature-old" in self.ctx.state["all_branches"]

    def test_skips_detached_head(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  (HEAD detached at abc123)\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert "(HEAD detached at abc123)" not in self.ctx.state["all_branches"]

    def test_skips_remote_tracking_branches(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  remotes/origin/feature-old\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert "remotes/origin/feature-old" not in self.ctx.state["all_branches"]

    def test_uses_config_threshold(self):
        self.ctx.config["stale_branch_days"] = 60

        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+00:00|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert "master" in self.ctx.state["all_branches"]

    def test_parses_git_iso_strict_output_with_delimiter(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n  feature-old\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = (
            "2024-01-01T10:00:00+00:00|master\n"
            "2024-01-01T10:00:00+00:00|feature-old\n"
        )
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert self.ctx.state["stale_branches"] == ["master", "feature-old"]

    def test_raises_on_missing_current_repo(self):
        ctx = make_context(config={"stale_branch_days": 30})
        skill = CheckStaleBranches("check_stale_branches", 4)
        with pytest.raises(SystemException, match="current_repo"):
            skill.execute(ctx)

    def test_raises_on_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git command not found"):
                skill.execute(self.ctx)

    def test_raises_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="timed out"):
                skill.execute(self.ctx)

    def test_raises_on_subprocess_error_for_each_ref(self):
        import subprocess
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        with patch("subprocess.run", side_effect=[
            mock_branch_result,
            subprocess.SubprocessError("for-each-ref failed"),
        ]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git for-each-ref failed"):
                skill.execute(self.ctx)
