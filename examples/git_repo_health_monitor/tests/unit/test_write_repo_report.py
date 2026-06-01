"""Unit tests for the WriteRepoReport skill."""

from unittest.mock import Mock

import pytest

from rpacore import SystemException
from skills.write_repo_report import WriteRepoReport

class TestWriteRepoReport:
    """Test the WriteRepoReport skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_computes_healthy_status(self):
        """Test that WriteRepoReport computes 'healthy' for 0 failures."""
        self.mock_ctx.data = {
            "current_repo": "/tmp/test_repo",
            "output_file": "/tmp/output.jsonl",
            "uncommitted_changes": [],
            "recent_commits": [{"commit_hash": "abc123", "subject": "Initial", "timestamp": "2024-01-01"}],
            "remotes": {"origin": "https://github.com/example/repo.git"},
            "stale_branches": [],
            "all_branches": ["master"],
        }

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["health_report"]["health_status"] == "healthy"

        # Verify stored in repo_health_records
        records = self.mock_ctx.data["repo_health_records"]
        assert len(records) == 1
        assert records[0]["health_status"] == "healthy"
        assert records[0]["repository"] == "/tmp/test_repo"

    def test_computes_degraded_status(self):
        """Test that WriteRepoReport computes 'degraded' for 1-2 failures."""
        self.mock_ctx.data = {
            "current_repo": "/tmp/test_repo",
            "output_file": "/tmp/output.jsonl",
            "uncommitted_changes": ["file1.txt"],  # 1 change
            "recent_commits": [],
            "remotes": {"origin": "https://github.com/example/repo.git"},
            "stale_branches": [],
            "all_branches": ["master"],
        }

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["health_report"]["health_status"] == "degraded"
        assert self.mock_ctx.data["repo_health_records"][0]["health_status"] == "degraded"

    def test_computes_unhealthy_status(self):
        """Test that WriteRepoReport computes 'unhealthy' for 3+ failures."""
        self.mock_ctx.data = {
            "current_repo": "/tmp/test_repo",
            "output_file": "/tmp/output.jsonl",
            "uncommitted_changes": ["file1.txt", "file2.txt", "file3.txt"],  # 3 changes (capped at 2)
            "recent_commits": [],
            "remotes": {},  # no remotes (+1)
            "stale_branches": ["old-branch"],  # stale branch (+1)
            "all_branches": ["master", "old-branch"],
        }

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.mock_ctx)

        # 2 (capped) + 1 (no remotes) + 1 (stale) = 4 -> unhealthy
        assert self.mock_ctx.data["health_report"]["health_status"] == "unhealthy"
        assert self.mock_ctx.data["repo_health_records"][0]["health_status"] == "unhealthy"

    def test_appends_to_repo_health_records(self):
        """Test that WriteRepoReport appends health records to repo_health_records list."""
        # First record
        self.mock_ctx.data = {
            "current_repo": "/tmp/repo1",
            "output_file": "/tmp/output.jsonl",
            "uncommitted_changes": [],
            "recent_commits": [],
            "remotes": {"origin": "https://example.com"},
            "stale_branches": [],
            "all_branches": ["master"],
        }
        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.mock_ctx)

        # Second record (same skill instance, new data)
        self.mock_ctx.data["current_repo"] = "/tmp/repo2"
        skill.execute(self.mock_ctx)

        records = self.mock_ctx.data["repo_health_records"]
        assert len(records) == 2
        assert records[0]["repository"] == "/tmp/repo1"
        assert records[1]["repository"] == "/tmp/repo2"

    def test_stores_last_commit_timestamp(self):
        """Test that WriteRepoReport stores the most recent commit timestamp."""
        self.mock_ctx.data = {
            "current_repo": "/tmp/test_repo",
            "output_file": "/tmp/output.jsonl",
            "uncommitted_changes": [],
            "recent_commits": [
                {"commit_hash": "abc123", "subject": "Latest", "timestamp": "2024-01-15T10:00:00+00:00"},
                {"commit_hash": "def456", "subject": "Older", "timestamp": "2024-01-14T10:00:00+00:00"},
            ],
            "remotes": {},
            "stale_branches": [],
            "all_branches": ["master"],
        }

        skill = WriteRepoReport("write_repo_report", 5)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["health_report"]["last_commit"] == "2024-01-15T10:00:00+00:00"
        assert self.mock_ctx.data["repo_health_records"][0]["last_commit"] == "2024-01-15T10:00:00+00:00"

    def test_raises_on_missing_current_repo(self):
        """Test that WriteRepoReport raises when current_repo is missing."""
        self.mock_ctx.data = {"output_file": "/tmp/output.jsonl"}
        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_repo" in str(exc_info.value)

    def test_raises_on_missing_output_file(self):
        """Test that WriteRepoReport raises when output_file is missing."""
        self.mock_ctx.data = {"current_repo": "/tmp/test_repo"}
        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No output_file" in str(exc_info.value)

    def test_output_file_still_validated(self):
        """Test that WriteRepoReport still validates output_file is present (for WriteSummary)."""
        self.mock_ctx.data = {
            "current_repo": "/tmp/test_repo",
            "uncommitted_changes": [],
            "recent_commits": [],
            "remotes": {},
            "stale_branches": [],
            "all_branches": ["master"],
        }

        skill = WriteRepoReport("write_repo_report", 5)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No output_file" in str(exc_info.value)
