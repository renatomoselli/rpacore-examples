from __future__ import annotations

"""Unit tests for the WriteOutput step."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from steps.write_output import WriteOutput


class TestWriteOutput:
    """Test the WriteOutput step."""

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
            },
        )
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={"results_dir": str(results_dir)},
        )
        Path(tmp_path / "inbox").mkdir(exist_ok=True)
        (tmp_path / "inbox" / "events_001.json").touch()

    def test_writes_jsonl_records(self) -> None:
        step = WriteOutput("write_output", 4)
        step.execute(self.ctx)
        output_file = Path(self.ctx.config["results_dir"]) / "events_001_cleaned.jsonl"
        assert output_file.exists()
        lines = output_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_id"] == "1"
        assert json.loads(lines[1])["event_id"] == "2"
        assert len(self.transaction.artifacts) == 1
        artifact = self.transaction.artifacts[0]
        assert artifact.name == "events_001_cleaned.jsonl"
        assert artifact.kind == "output"
        assert artifact.metadata["event_count"] == 2
        assert artifact.metadata["source_file"] == self.transaction.state["current_file"]

    def test_creates_output_file_in_results_dir(self) -> None:
        step = WriteOutput("write_output", 4)
        step.execute(self.ctx)
        assert (Path(self.ctx.config["results_dir"]) / "events_001_cleaned.jsonl").exists()

    def test_raises_on_missing_normalized_events(self) -> None:
        self.transaction.state = {"current_file": "/tmp/test.json"}
        step = WriteOutput("write_output", 4)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Missing required state key: normalized_events" in str(exc_info.value)

    def test_raises_on_missing_context(self) -> None:
        self.transaction.state = {"normalized_events": [{"event_id": "1"}]}
        step = WriteOutput("write_output", 4)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Missing required state key: current_file" in str(exc_info.value)

    def test_raises_on_missing_results_dir_config(self) -> None:
        self.ctx = ProcessContext(transaction=self.transaction, config={})
        step = WriteOutput("write_output", 4)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Missing required config key: results_dir" in str(exc_info.value)

    def test_writes_empty_jsonl_on_empty_events(self) -> None:
        self.transaction.state["normalized_events"] = []
        step = WriteOutput("write_output", 4)
        step.execute(self.ctx)
        output_file = Path(self.ctx.config["results_dir"]) / "events_001_cleaned.jsonl"
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8").strip() == ""

    @pytest.mark.parametrize("failure_target", ["rpacore.paths.os.fsync", "rpacore.paths.os.replace"])
    def test_keeps_previous_output_and_removes_temporary_on_publication_failure(
        self,
        failure_target: str,
    ) -> None:
        output_file = Path(self.ctx.config["results_dir"]) / "events_001_cleaned.jsonl"
        output_file.write_text("previous\n", encoding="utf-8")

        with patch(failure_target, side_effect=OSError("publication failed")):
            with pytest.raises(SystemException, match="publication failed"):
                WriteOutput("write_output", 4).execute(self.ctx)

        assert output_file.read_text(encoding="utf-8") == "previous\n"
        assert list(output_file.parent.glob(".*.tmp")) == []
