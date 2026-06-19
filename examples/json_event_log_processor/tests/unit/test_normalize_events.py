from __future__ import annotations

"""Unit tests for the NormalizeEvents skill."""

from unittest.mock import patch

import pytest

from rpacore import ProcessContext, SystemException, Transaction

from skills.normalize_events import NormalizeEvents


class TestNormalizeEvents:
    """Test the NormalizeEvents skill."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.transaction = Transaction(
            reference="test",
            state={
                "events": [
                    {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {"message": "ok"}},
                    {"event_id": "2", "event_type": "error", "timestamp": "2024-01-02T00:00:00Z", "source": "svc", "payload": {"error": "fail"}},
                ],
                "current_file": "test_events.json",
            },
        )
        self.ctx = ProcessContext(transaction=self.transaction)

    def test_normalizes_valid_events(self) -> None:
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        normalized = self.ctx.state["normalized_events"]
        assert len(normalized) == 2
        assert normalized[0]["event_id"] == "1"
        assert normalized[0]["severity"] == "INFO"
        assert normalized[0]["version"] == "1.0"
        assert "processed_at" in normalized[0]

    def test_parses_iso8601_timestamp_with_z_suffix(self) -> None:
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        assert "timestamp" in self.ctx.state["normalized_events"][0]

    def test_parses_iso8601_timestamp_with_offset(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00+00:00", "source": "svc", "payload": {}},
        ]
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        assert "timestamp" in self.ctx.state["normalized_events"][0]

    def test_maps_event_type_to_severity(self) -> None:
        for event_type, expected_severity in [("info", "INFO"), ("warning", "WARNING"), ("error", "ERROR")]:
            self.transaction.state["events"] = [
                {"event_id": "1", "event_type": event_type, "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {}},
            ]
            skill = NormalizeEvents("normalize_events", 3)
            skill.execute(self.ctx)
            assert self.ctx.state["normalized_events"][0]["severity"] == expected_severity

    def test_adds_processed_at_and_version(self) -> None:
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        normalized = self.ctx.state["normalized_events"][0]
        assert "processed_at" in normalized
        assert normalized["version"] == "1.0"

    def test_flattens_payload(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {"key": "value", "nested": {"a": 1}}},
        ]
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        assert self.ctx.state["normalized_events"][0]["payload"] == {"key": "value", "nested": {"a": 1}}

    def test_non_dict_payload_logs_warning_and_uses_empty_payload(self) -> None:
        self.transaction.state["events"] = [
            {
                "event_id": "1",
                "event_type": "info",
                "timestamp": "2024-01-01T00:00:00Z",
                "source": "svc",
                "payload": "not-a-dict",
            },
        ]

        with patch("skills.normalize_events.logger.warning") as mock_warning:
            skill = NormalizeEvents("normalize_events", 3)
            skill.execute(self.ctx)

        assert self.ctx.state["normalized_events"][0]["payload"] == {}
        mock_warning.assert_called_once()
        assert "non-dict payload" in mock_warning.call_args.args[0]

    def test_raises_when_no_events_in_context(self) -> None:
        self.transaction.state = {}
        skill = NormalizeEvents("normalize_events", 3)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Missing required state key: events" in str(exc_info.value)

    def test_raises_on_invalid_timestamp(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "info", "timestamp": "not-a-timestamp", "source": "svc", "payload": {}},
        ]
        skill = NormalizeEvents("normalize_events", 3)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Failed to parse timestamp" in str(exc_info.value)

    def test_raises_system_exception_for_unmapped_event_type(self) -> None:
        self.transaction.state["events"] = [
            {
                "event_id": "1",
                "event_type": "critical",
                "timestamp": "2024-01-01T00:00:00Z",
                "source": "svc",
                "payload": {},
            },
        ]
        skill = NormalizeEvents("normalize_events", 3)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Unsupported event_type" in str(exc_info.value)

    def test_raises_system_exception_for_non_dict_event(self) -> None:
        self.transaction.state["events"] = [1]
        skill = NormalizeEvents("normalize_events", 3)
        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)
        assert "Expected event object" in str(exc_info.value)

    def test_handles_missing_current_file(self) -> None:
        self.transaction.state.pop("current_file", None)
        skill = NormalizeEvents("normalize_events", 3)
        skill.execute(self.ctx)
        normalized = self.ctx.state["normalized_events"]
        assert len(normalized) == 2
