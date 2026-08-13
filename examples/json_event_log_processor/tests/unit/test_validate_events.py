from __future__ import annotations

"""Unit tests for the ValidateEvents step."""

import pytest

from rpacore import BusinessException, ProcessContext, Transaction

from steps.validate_events import ValidateEvents


class TestValidateEvents:
    """Test the ValidateEvents step."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.transaction = Transaction(
            reference="test",
            state={"events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc", "payload": {}},
                {"event_id": "2", "event_type": "error", "timestamp": "2024-01-02T00:00:00Z", "source": "svc", "payload": {}},
            ]},
        )
        self.ctx = ProcessContext(transaction=self.transaction)

    def test_passes_for_valid_events(self) -> None:
        step = ValidateEvents("validate_events", 2)
        step.execute(self.ctx)

    def test_raises_on_missing_event_id(self) -> None:
        self.transaction.state["events"] = [
            {"event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc"},
        ]
        self.transaction.metadata["event_count"] = 1
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "missing required field: event_id" in str(exc_info.value)
        assert "events" not in self.transaction.state
        assert "event_count" not in self.transaction.metadata

    def test_raises_on_missing_event_type(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "timestamp": "2024-01-01T00:00:00Z", "source": "svc"},
        ]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "missing required field: event_type" in str(exc_info.value)

    def test_raises_on_missing_timestamp(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "info", "source": "svc"},
        ]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "missing required field: timestamp" in str(exc_info.value)

    def test_raises_on_missing_source(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z"},
        ]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "missing required field: source" in str(exc_info.value)

    def test_raises_on_invalid_event_type(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "1", "event_type": "critical", "timestamp": "2024-01-01T00:00:00Z", "source": "svc"},
        ]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "invalid event_type" in str(exc_info.value)

    def test_raises_on_empty_event_list(self) -> None:
        self.transaction.state["events"] = []
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "empty" in str(exc_info.value)

    def test_raises_when_no_events_in_context(self) -> None:
        self.transaction.state = {}
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "No events in context" in str(exc_info.value)

    def test_raises_on_non_dict_event(self) -> None:
        self.transaction.state["events"] = ["not a dict", {"event_id": "1"}]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "is not an object" in str(exc_info.value)

    def test_raises_on_empty_string_required_field(self) -> None:
        self.transaction.state["events"] = [
            {"event_id": "", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "svc"},
        ]
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert "missing required field: event_id" in str(exc_info.value)

    def test_stop_true_causes_engine_skip_downstream(self) -> None:
        self.transaction.state["events"] = []
        step = ValidateEvents("validate_events", 2)
        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)
        assert exc_info.value.halts_remaining_steps is True
