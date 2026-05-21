"""Unit tests for the WriteOutput skill."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from oref import SystemException
from skills.write_output import WriteOutput


class TestWriteOutput:
    """Test the WriteOutput skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_writes_jsonl_records(self, tmp_path):
        """Test that WriteOutput writes normalized events as JSONL."""
        results_dir = str(tmp_path / "results")
        Path(results_dir).mkdir()
        self.mock_ctx.data = {
            "normalized_events": [
                {"event_id": "1", "severity": "INFO", "timestamp": "2024-01-01T00:00:00+00:00"},
                {"event_id": "2", "severity": "ERROR", "timestamp": "2024-01-01T01:00:00+00:00"},
            ],
            "current_file": str(tmp_path / "inbox" / "events_001.json"),
            "results_dir": results_dir,
        }
        Path(tmp_path / "inbox").mkdir()
        (tmp_path / "inbox" / "events_001.json").touch()

        skill = WriteOutput("write_output", 4)
        skill.execute(self.mock_ctx)

        output_file = Path(results_dir) / "events_001_cleaned.jsonl"
        assert output_file.exists()
        lines = output_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_id"] == "1"
        assert json.loads(lines[1])["event_id"] == "2"

    def test_creates_output_file_in_results_dir(self, tmp_path):
        """Test that WriteOutput creates the output file in the results directory."""
        results_dir = str(tmp_path / "results")
        Path(results_dir).mkdir()
        self.mock_ctx.data = {
            "normalized_events": [{"event_id": "1", "severity": "INFO"}],
            "current_file": str(tmp_path / "inbox" / "test.json"),
            "results_dir": results_dir,
        }
        Path(tmp_path / "inbox").mkdir()
        (tmp_path / "inbox" / "test.json").touch()

        skill = WriteOutput("write_output", 4)
        skill.execute(self.mock_ctx)

        assert (Path(results_dir) / "test_cleaned.jsonl").exists()

    def test_raises_on_missing_normalized_events(self):
        """Test that WriteOutput raises SystemException when normalized_events is missing."""
        self.mock_ctx.data = {"current_file": "/tmp/test.json", "results_dir": "/tmp/results"}
        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No normalized_events" in str(exc_info.value)

    def test_raises_on_missing_context(self):
        """Test that WriteOutput raises SystemException when current_file or results_dir is missing."""
        self.mock_ctx.data = {"normalized_events": [{"event_id": "1"}]}
        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Missing current_file" in str(exc_info.value)
