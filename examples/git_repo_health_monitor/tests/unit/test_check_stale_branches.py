"""Unit tests for the CheckStaleBranches skill."""

from datetime import datetime, timedelta, timezone
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
        assert self.ctx.state["stale_branches"] == ["master"]

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

        recent_enough = datetime.now(timezone.utc) - timedelta(days=30)
        mock_ref_result = Mock()
        mock_ref_result.stdout = f"{recent_enough.isoformat()}|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert "master" in self.ctx.state["all_branches"]
        assert self.ctx.state["stale_branches"] == []

    def test_uses_exact_age_cutoff_without_midnight_blind_spot(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        just_stale = datetime.now(timezone.utc) - timedelta(days=30, minutes=5)
        mock_ref_result = Mock()
        mock_ref_result.stdout = f"{just_stale.isoformat()}|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert self.ctx.state["stale_branches"] == ["master"]

    def test_skips_invalid_for_each_ref_dates(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "not-a-date|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert self.ctx.state["stale_branches"] == []

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

    def test_parses_git_dates_with_compact_timezone_offset(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.stdout = "2024-01-01T10:00:00+0000|master\n"
        mock_ref_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            skill.execute(self.ctx)

        assert self.ctx.state["stale_branches"] == ["master"]

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

    def test_raises_on_nonzero_git_branch_exit(self):
        mock_branch_result = Mock()
        mock_branch_result.returncode = 128
        mock_branch_result.stderr = "fatal: not a git repository"

        with patch("subprocess.run", return_value=mock_branch_result):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git branch returned exit code 128"):
                skill.execute(self.ctx)

    def test_raises_on_os_error_for_branch_list(self):
        with patch("subprocess.run", side_effect=PermissionError("denied")):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git branch failed"):
                skill.execute(self.ctx)

    def test_raises_on_os_error_for_each_ref(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        with patch("subprocess.run", side_effect=[
            mock_branch_result,
            PermissionError("denied"),
        ]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git for-each-ref failed"):
                skill.execute(self.ctx)

    def test_raises_on_missing_git_for_each_ref(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        with patch("subprocess.run", side_effect=[mock_branch_result, FileNotFoundError()]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git command not found"):
                skill.execute(self.ctx)

    def test_raises_on_timeout_for_each_ref(self):
        import subprocess
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        with patch("subprocess.run", side_effect=[
            mock_branch_result,
            subprocess.TimeoutExpired("git", 30),
        ]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git for-each-ref timed out"):
                skill.execute(self.ctx)

    def test_raises_on_nonzero_for_each_ref_exit(self):
        mock_branch_result = Mock()
        mock_branch_result.stdout = "* master\n"
        mock_branch_result.returncode = 0

        mock_ref_result = Mock()
        mock_ref_result.returncode = 128
        mock_ref_result.stderr = "fatal: not a git repository"

        with patch("subprocess.run", side_effect=[mock_branch_result, mock_ref_result]):
            skill = CheckStaleBranches("check_stale_branches", 4)
            with pytest.raises(SystemException, match="git for-each-ref returned exit code 128"):
                skill.execute(self.ctx)
