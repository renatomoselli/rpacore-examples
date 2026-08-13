from __future__ import annotations

"""Unit tests for the LoadJsonFile step."""

import json
from pathlib import Path

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from steps.load_json_file import LoadJsonFile


class TestLoadJsonFile:
    """Test the LoadJsonFile step."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.test_file = tmp_path / "test_events.json"
        self.test_file.write_text(
            json.dumps([{"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {}}, {"event_id": "2", "event_type": "error", "timestamp": "2024-01-02T00:00:00Z", "source": "svc", "payload": {}}]),
            encoding="utf-8",
        )
        self.transaction = Transaction(
            reference="test",
            state={"current_file": str(self.test_file)},
        )
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={"inbox_dir": str(tmp_path)},
        )

    def test_loads_valid_json_array(self) -> None:
        step = LoadJsonFile("load_json_file", 1)
        step.execute(self.ctx)
        assert len(self.ctx.state["events"]) == 2
        assert self.ctx.state["events"][0]["event_id"] == "1"
        assert self.ctx.state["events"][1]["event_id"] == "2"
        assert self.ctx.transaction.metadata["event_count"] == 2

    def test_loads_valid_single_event_object(self, tmp_path: Path) -> None:
        event = {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {}}
        self.test_file.write_text(json.dumps(event), encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        step.execute(self.ctx)
        assert self.ctx.state["events"] == [event]

    def test_raises_on_file_not_found(self) -> None:
        self.transaction.state["current_file"] = str(Path(self.ctx.config["inbox_dir"]) / "nonexistent.json")
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "File not found" in str(exc_info.value)

    def test_raises_on_malformed_json(self) -> None:
        self.test_file.write_text("{invalid json", encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Malformed JSON" in str(exc_info.value)

    def test_raises_on_no_current_file(self) -> None:
        self.transaction.state = {}
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Missing required state key: current_file" in str(exc_info.value)

    def test_requires_inbox_dir_config(self) -> None:
        self.ctx = ProcessContext(transaction=self.transaction, config={})
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Missing required config key: inbox_dir" in str(exc_info.value)

    def test_rejects_file_outside_inbox(self, tmp_path: Path) -> None:
        outside_file = tmp_path / "outside.json"
        outside_file.write_text("[]", encoding="utf-8")
        inbox_dir = tmp_path / "inbox"
        inbox_dir.mkdir()
        self.transaction.state["current_file"] = str(outside_file)
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={"inbox_dir": str(inbox_dir)},
        )

        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "escapes inbox directory" in str(exc_info.value)

    def test_passes_through_non_dict_list_items(self) -> None:
        self.test_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        step.execute(self.ctx)
        assert self.ctx.state["events"] == [1, 2, 3]

    def test_raises_on_scalar_json_value(self) -> None:
        self.test_file.write_text(json.dumps("just a string"), encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Expected JSON object or array" in str(exc_info.value)

    def test_raises_on_scalar_json_number(self) -> None:
        self.test_file.write_text(json.dumps(42), encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Expected JSON object or array" in str(exc_info.value)

    def test_raises_on_scalar_json_null(self) -> None:
        self.test_file.write_text(json.dumps(None), encoding="utf-8")
        step = LoadJsonFile("load_json_file", 1)
        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)
        assert "Expected JSON object or array" in str(exc_info.value)
