"""Unit tests for the WriteSummary skill."""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.write_summary import WriteSummary

class TestWriteSummary:
    """Test the WriteSummary skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_writes_summary_json(self, tmp_path):
        """Test that WriteSummary writes a summary JSON file atomically."""
        output_file = str(tmp_path / "health_report.jsonl")
        self.mock_ctx.data = {
            "repo_health_records": [
                {
                    "repository": "/tmp/alpha",
                    "health_status": "healthy",
                    "uncommitted_changes": 0,
                },
                {
                    "repository": "/tmp/beta",
                    "health_status": "degraded",
                    "uncommitted_changes": 1,
                },
                {
                    "repository": "/tmp/gamma",
                    "health_status": "unhealthy",
                    "uncommitted_changes": 3,
                },
            ],
            "output_file": output_file,
        }

        skill = WriteSummary("write_summary", 1)
        skill.execute(self.mock_ctx)

        summary_path = str(Path(output_file).with_suffix(".summary.json"))
        assert Path(summary_path).exists()

        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["summary"] is True
        assert summary["total_repos"] == 3
        assert summary["healthy"] == 1
        assert summary["degraded"] == 1
        assert summary["unhealthy"] == 1
        assert len(summary["repo_details"]) == 3

    def test_handles_empty_records(self, tmp_path):
        """Test that WriteSummary handles missing repo_health_records gracefully."""
        output_file = str(tmp_path / "health_report.jsonl")
        self.mock_ctx.data = {
            "output_file": output_file,
            # repo_health_records not set — null guard should handle this
        }

        skill = WriteSummary("write_summary", 1)
        skill.execute(self.mock_ctx)

        summary_path = str(Path(output_file).with_suffix(".summary.json"))
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["total_repos"] == 0
        assert summary["healthy"] == 0
        assert summary["degraded"] == 0
        assert summary["unhealthy"] == 0

    def test_raises_on_missing_output_file(self):
        """Test that WriteSummary raises when output_file is missing."""
        self.mock_ctx.data = {"repo_health_records": []}
        skill = WriteSummary("write_summary", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No output_file" in str(exc_info.value)

    def test_raises_on_io_error(self, tmp_path, monkeypatch):
        """Test that WriteSummary raises SystemException when os.replace fails."""
        output_file = str(tmp_path / "health_report.jsonl")
        self.mock_ctx.data = {
            "repo_health_records": [
                {"repository": "/tmp/test", "health_status": "healthy"},
            ],
            "output_file": output_file,
        }

        def mock_replace(src, dst):
            raise OSError("Permission denied")

        monkeypatch.setattr(os, "replace", mock_replace)

        skill = WriteSummary("write_summary", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Failed to write summary report" in str(exc_info.value)

        # Temp file should be cleaned up
        tmp_files = list(tmp_path.glob(".summary_*.tmp"))
        assert len(tmp_files) == 0
