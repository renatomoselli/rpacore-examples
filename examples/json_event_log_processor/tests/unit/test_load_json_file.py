"""Unit tests for the LoadJsonFile skill."""

import json
from pathlib import Path

import pytest

from rpacore import SystemException
from skills.load_json_file import LoadJsonFile


class TestLoadJsonFile:
    """Test the LoadJsonFile skill."""

    def setup_method(self):
        """Set up test fixtures."""
        from unittest.mock import Mock
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_loads_valid_json_array(self, tmp_path):
        """Test that LoadJsonFile loads a JSON array of events."""
        events = [
            {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            {"event_id": "2", "event_type": "error", "timestamp": "2024-01-01T01:00:00Z", "source": "test"},
        ]
        test_file = tmp_path / "test_events.json"
        test_file.write_text(json.dumps(events), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["events"] == events
        assert len(self.mock_ctx.data["events"]) == 2

    def test_loads_valid_single_event_object(self, tmp_path):
        """Test that LoadJsonFile loads a single event object as an array."""
        event = {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"}
        test_file = tmp_path / "test_event.json"
        test_file.write_text(json.dumps(event), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["events"] == [event]

    def test_raises_on_file_not_found(self):
        """Test that LoadJsonFile raises SystemException for missing files."""
        self.mock_ctx.data = {"current_file": "/nonexistent/path/events.json"}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "File not found" in str(exc_info.value)

    def test_raises_on_malformed_json(self, tmp_path):
        """Test that LoadJsonFile raises SystemException for corrupt JSON."""
        test_file = tmp_path / "test_events.json"
        test_file.write_text("{invalid json", encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Malformed JSON" in str(exc_info.value)

    def test_raises_on_no_current_file(self):
        """Test that LoadJsonFile raises SystemException when current_file is missing."""
        self.mock_ctx.data = {}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No current_file" in str(exc_info.value)

    def test_passes_through_non_dict_list_items(self, tmp_path):
        """Test that LoadJsonFile passes through raw data without schema validation."""
        test_file = tmp_path / "test_events.json"
        test_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)
        skill.execute(self.mock_ctx)  # Should succeed — data is a list

        assert self.mock_ctx.data["events"] == [1, 2, 3]

    def test_raises_on_scalar_json_value(self, tmp_path):
        """Test that LoadJsonFile raises SystemException for scalar JSON values. [Q14]"""
        test_file = tmp_path / "test_scalar.json"
        test_file.write_text(json.dumps("just a string"), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Expected JSON object or array" in str(exc_info.value)

    def test_raises_on_scalar_json_number(self, tmp_path):
        """Test that LoadJsonFile raises SystemException for JSON number. [Q14]"""
        test_file = tmp_path / "test_number.json"
        test_file.write_text(json.dumps(42), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Expected JSON object or array" in str(exc_info.value)

    def test_raises_on_scalar_json_null(self, tmp_path):
        """Test that LoadJsonFile raises SystemException for JSON null. [Q14]"""
        test_file = tmp_path / "test_null.json"
        test_file.write_text(json.dumps(None), encoding="utf-8")

        self.mock_ctx.data = {"current_file": str(test_file)}
        skill = LoadJsonFile("load_json_file", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Expected JSON object or array" in str(exc_info.value)
