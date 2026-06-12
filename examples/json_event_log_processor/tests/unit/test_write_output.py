"""Unit tests for the WriteOutput skill."""

import json
from pathlib import Path

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from skills.write_output import WriteOutput


class TestWriteOutput:
    """Test the WriteOutput skill."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        self.transaction = Transaction(
            reference="test",
            state={
                "normalized_events": [
                    {"event_id": "1", "severity": "INFO", "payload": {}},
                    {"event_id": "2", "severity": "ERROR", "payload": {"error": "fail"}},
                ],
                "current_file": str(tmp_path / "inbox" / "events_001.json"),
                "results_dir": str(results_dir),
            },
        )
        self.ctx = ProcessContext(transaction=self.transaction, config={})
        Path(tmp_path / "inbox").mkdir(exist_ok=True)
        (tmp_path / "inbox" / "events_001.json").touch()

    def test_writes_jsonl_records(self) -> None:
        skill = WriteOutput("write_output", 4)
        skill.execute(self.ctx)
        output_file = Path(self.ctx.state["results_dir"]) / "events_001_cleaned.jsonl"
        assert output_file.exists()
        lines = output_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_id"] == "1"
        assert json.loads(lines[1])["event_id"] == "2"

    def test_creates_output_file_in_results_dir(self) -> None:
        skill = WriteOutput("write_output", 4)
        skill.execute(self.ctx)
        assert (Path(self.ctx.state["results_dir"]) / "events_001_cleaned.jsonl").exists()

    def test_raises_on_missing_normalized_events(self) -> None:
        self.transaction.state = {"current_file": "/tmp/test.json", "results_dir": "/tmp/results"}
        skill = WriteOutput("write_output", 4)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Missing required state key: normalized_events" in str(exc_info.value)

    def test_raises_on_missing_context(self) -> None:
        self.transaction.state = {"normalized_events": [{"event_id": "1"}]}
        skill = WriteOutput("write_output", 4)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Missing required state key: current_file" in str(exc_info.value)

    def test_writes_empty_jsonl_on_empty_events(self) -> None:
        self.transaction.state["normalized_events"] = []
        skill = WriteOutput("write_output", 4)
        skill.execute(self.ctx)
        output_file = Path(self.ctx.state["results_dir"]) / "events_001_cleaned.jsonl"
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8").strip() == ""
