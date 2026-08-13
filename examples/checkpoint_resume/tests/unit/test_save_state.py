from __future__ import annotations

import json
import pytest
from rpacore import Status

from steps.save_state import SaveState


class TestSaveState:
    """Tests for the SaveState step."""

    def test_execute_increments_counter(self, run_step, sample_checkpoint_path) -> None:
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert "counter" in tx.state
        assert isinstance(tx.state["counter"], dict)
        assert tx.state["counter"]["value"] == 1

    def test_execute_appends_to_existing_counter(self, run_step, sample_checkpoint_path) -> None:
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            state={"counter": {"value": 5, "timestamp": "2024-01-01T00:00:00+00:00"}},
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["counter"]["value"] == 6

    def test_execute_writes_checkpoint_file(self, run_step, sample_checkpoint_path) -> None:
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert sample_checkpoint_path.exists()
        data = json.loads(sample_checkpoint_path.read_text())
        assert data["value"] == 1
        assert "timestamp" in data

    def test_execute_records_artifact(self, run_step, sample_checkpoint_path) -> None:
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert len(tx.artifacts) == 1
        artifact = tx.artifacts[0]
        assert artifact.name == "checkpoint"
        assert artifact.kind == "json"
        assert artifact.path == str(sample_checkpoint_path)
        assert artifact.metadata["counter"] == 1

    def test_execute_fails_without_state_update_when_checkpoint_write_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        run_step,
        sample_checkpoint_path,
    ) -> None:
        sample_checkpoint_path.write_text("last valid checkpoint", encoding="utf-8")

        def fail_dump(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("steps.save_state.json.dump", fail_dump)

        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )

        assert tx.status == Status.FAILED
        assert tx.state == {}
        assert tx.artifacts == []
        assert sample_checkpoint_path.read_text(encoding="utf-8") == "last valid checkpoint"
        assert not list(sample_checkpoint_path.parent.glob(".checkpoint.json.*.tmp"))

    def test_execute_with_missing_value_key(self, run_step, sample_checkpoint_path) -> None:
        """Counter with no 'value' key should default to 0."""
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            state={"counter": {"timestamp": "2024-01-01T00:00:00+00:00"}},
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["counter"]["value"] == 1

    def test_execute_with_missing_timestamp(self, run_step, sample_checkpoint_path) -> None:
        """Counter with no 'timestamp' key should be replaced entirely."""
        tx = run_step(
            SaveState(name="save_state", execution_order=1),
            state={"counter": {"value": 3}},
            config={"checkpoint_path": str(sample_checkpoint_path)},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["counter"]["value"] == 4
        assert "timestamp" in tx.state["counter"]
