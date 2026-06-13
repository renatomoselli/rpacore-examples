"""Unit tests for the WriteRepoReport skill."""

import pytest

from rpacore import BusinessException, SystemException
from skills.write_repo_report import WriteRepoReport
from tests.conftest import make_context


class TestWriteRepoReport:
    """Test the WriteRepoReport skill."""

    def setup_method(self):
        self.ctx = make_context(state={
            "current_repo": "/tmp/test_repo",
            "output_file": "/tmp/output.jsonl",
        })

    def test_computes_healthy_status(self):
        """Test that WriteRepoReport computes 'healthy' for 0 failures."""
        self.ctx.state["uncommitted_changes"] = []
        self.ctx.state["recent_commits"] = [
            {"commit_hash": "abc123", "subject": "Initial", "timestamp": "2024-01-01"},
        ]
        self.ctx.state["remotes"] = {"origin": "https://github.com/example/repo.git"}
        self.ctx.state["stale_branches"] = []
        self.ctx.state["all_branches"] = ["master"]

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.ctx)

        assert self.ctx.state["health_report"]["health_status"] == "healthy"
        assert self.ctx.state["health_report"]["repository"] == "/tmp/test_repo"
        assert self.ctx.transaction.metadata["repo_name"] == "test_repo"
        assert self.ctx.transaction.metadata["health_status"] == "healthy"

    def test_computes_degraded_status_and_raises(self):
        """Test that WriteRepoReport raises BusinessException for degraded repos."""
        self.ctx.state["uncommitted_changes"] = ["file1.txt"]
        self.ctx.state["recent_commits"] = []
        self.ctx.state["remotes"] = {"origin": "https://github.com/example/repo.git"}
        self.ctx.state["stale_branches"] = []
        self.ctx.state["all_branches"] = ["master"]

        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.ctx)

        assert exc_info.value.stop is True
        assert "degraded" in str(exc_info.value).lower()
        # Health data is persisted before the raise
        assert self.ctx.state["health_report"]["health_status"] == "degraded"

    def test_computes_unhealthy_status_and_raises(self):
        """Test that WriteRepoReport raises BusinessException for unhealthy repos."""
        self.ctx.state["uncommitted_changes"] = ["f1.txt", "f2.txt", "f3.txt"]
        self.ctx.state["recent_commits"] = []
        self.ctx.state["remotes"] = {}
        self.ctx.state["stale_branches"] = ["old-branch"]
        self.ctx.state["all_branches"] = ["master", "old-branch"]

        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.ctx)

        assert exc_info.value.stop is True
        assert "unhealthy" in str(exc_info.value).lower()
        # Health data persisted before raise
        assert self.ctx.state["health_report"]["health_status"] == "unhealthy"

    def test_stores_last_commit_timestamp(self):
        """Test that WriteRepoReport stores the most recent commit timestamp."""
        self.ctx.state["uncommitted_changes"] = []
        self.ctx.state["recent_commits"] = [
            {"commit_hash": "abc123", "subject": "Latest", "timestamp": "2024-01-15T10:00:00+00:00"},
            {"commit_hash": "def456", "subject": "Older", "timestamp": "2024-01-14T10:00:00+00:00"},
        ]
        self.ctx.state["remotes"] = {}
        self.ctx.state["stale_branches"] = []
        self.ctx.state["all_branches"] = ["master"]

        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(BusinessException):
            skill.execute(self.ctx)

        assert self.ctx.state["health_report"]["last_commit"] == "2024-01-15T10:00:00+00:00"

    def test_does_not_accumulate_repo_health_records(self):
        """Test that WriteRepoReport no longer accumulates repo_health_records list."""
        self.ctx.state["uncommitted_changes"] = []
        self.ctx.state["recent_commits"] = []
        self.ctx.state["remotes"] = {"origin": "https://example.com"}
        self.ctx.state["stale_branches"] = []
        self.ctx.state["all_branches"] = ["master"]

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.ctx)

        # Should NOT have repo_health_records \u2014 that's main.py's job now
        assert "repo_health_records" not in self.ctx.state

    def test_raises_on_missing_current_repo(self):
        ctx = make_context(state={"output_file": "/tmp/output.jsonl"})
        skill = WriteRepoReport("write_repo_report", 5)
        with pytest.raises(SystemException, match="current_repo"):
            skill.execute(ctx)

    def test_raises_on_missing_output_file(self):
        ctx = make_context(state={"current_repo": "/tmp/test_repo"})
        skill = WriteRepoReport("write_repo_report", 5)
        with pytest.raises(SystemException, match="output_file"):
            skill.execute(ctx)
