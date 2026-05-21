"""Unit tests for the NormalizeEvents skill."""

import pytest

from oref import SystemException
from skills.normalize_events import NormalizeEvents


class TestNormalizeEvents:
    """Test the NormalizeEvents skill."""

    def setup_method(self):
        """Set up test fixtures."""
        from unittest.mock import Mock
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_normalizes_valid_events(self):
        """Test that NormalizeEvents normalizes all events."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.mock_ctx)

        normalized = self.mock_ctx.data["normalized_events"]
        assert len(normalized) == 1
        assert normalized[0]["event_id"] == "1"
        assert normalized[0]["severity"] == "INFO"
        assert normalized[0]["version"] == "1.0"
        assert "processed_at" in normalized[0]

    def test_parses_iso8601_timestamp_with_z_suffix(self):
        """Test that NormalizeEvents parses timestamps with Z suffix."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.mock_ctx)

        # Should not raise
        assert "timestamp" in self.mock_ctx.data["normalized_events"][0]

    def test_parses_iso8601_timestamp_with_offset(self):
        """Test that NormalizeEvents parses timestamps with timezone offset."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00+00:00", "source": "test"},
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.mock_ctx)

        assert "timestamp" in self.mock_ctx.data["normalized_events"][0]

    def test_maps_event_type_to_severity(self):
        """Test that NormalizeEvents maps event_type to severity codes."""
        for event_type, expected_severity in [("info", "INFO"), ("warning", "WARNING"), ("error", "ERROR")]:
            self.mock_ctx.data = {
                "events": [
                    {"event_id": "1", "event_type": event_type, "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
                ]
            }
            skill = NormalizeEvents("normalize_events", 3)
            skill.execute(self.mock_ctx)

            assert self.mock_ctx.data["normalized_events"][0]["severity"] == expected_severity

    def test_adds_processed_at_and_version(self):
        """Test that NormalizeEvents adds processed_at and version fields."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.mock_ctx)

        normalized = self.mock_ctx.data["normalized_events"][0]
        assert "processed_at" in normalized
        assert normalized["version"] == "1.0"

    def test_flattens_payload(self):
        """Test that NormalizeEvents flattens the payload field."""
        self.mock_ctx.data = {
            "events": [
                {
                    "event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z",
                    "source": "test", "payload": {"key": "value", "nested": {"a": 1}},
                },
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["normalized_events"][0]["payload"] == {"key": "value", "nested": {"a": 1}}

    def test_raises_when_no_events_in_context(self):
        """Test that NormalizeEvents raises SystemException when events is missing."""
        self.mock_ctx.data = {}
        skill = NormalizeEvents("normalize_events", 3)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No events" in str(exc_info.value)

    def test_raises_on_validation_failed_flag(self):
        """Test that NormalizeEvents raises SystemException when validation_failed is True."""
        self.mock_ctx.data = {
            "validation_failed": True,
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = NormalizeEvents("normalize_events", 3)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "Validation failed" in str(exc_info.value)
