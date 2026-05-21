"""Unit tests for the ValidateEvents skill."""

import pytest

from oref import BusinessException
from skills.validate_events import ValidateEvents


class TestValidateEvents:
    """Test the ValidateEvents skill."""

    def setup_method(self):
        """Set up test fixtures."""
        from unittest.mock import Mock
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_passes_for_valid_events(self):
        """Test that ValidateEvents passes for valid events and sets validation_failed=False."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
                {"event_id": "2", "event_type": "error", "timestamp": "2024-01-01T01:00:00Z", "source": "test"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)
        skill.execute(self.mock_ctx)  # Should not raise

        # On success, validation_failed is set to False
        assert self.mock_ctx.data["validation_failed"] is False

    def test_sets_validation_failed_true_on_missing_event_id(self):
        """Test that ValidateEvents sets validation_failed=True before raising on missing event_id."""
        self.mock_ctx.data = {
            "events": [
                {"event_type": "info", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        # Flag is set before raising, so NormalizeEvents can detect it
        assert self.mock_ctx.data["validation_failed"] is True
        assert "missing required field: event_id" in str(exc_info.value)

    def test_raises_on_missing_event_type(self):
        """Test that ValidateEvents raises BusinessException for missing event_type."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "missing required field: event_type" in str(exc_info.value)
        assert self.mock_ctx.data["validation_failed"] is True

    def test_raises_on_missing_timestamp(self):
        """Test that ValidateEvents raises BusinessException for missing timestamp."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "source": "test"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "missing required field: timestamp" in str(exc_info.value)

    def test_raises_on_missing_source(self):
        """Test that ValidateEvents raises BusinessException for missing source."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "info", "timestamp": "2024-01-01T00:00:00Z"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "missing required field: source" in str(exc_info.value)

    def test_raises_on_invalid_event_type(self):
        """Test that ValidateEvents raises BusinessException for invalid event_type."""
        self.mock_ctx.data = {
            "events": [
                {"event_id": "1", "event_type": "critical", "timestamp": "2024-01-01T00:00:00Z", "source": "test"},
            ]
        }
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "invalid event_type" in str(exc_info.value)

    def test_raises_on_empty_event_list(self):
        """Test that ValidateEvents raises BusinessException for empty event list."""
        self.mock_ctx.data = {"events": []}
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "empty" in str(exc_info.value)

    def test_raises_when_no_events_in_context(self):
        """Test that ValidateEvents raises BusinessException when events is missing."""
        self.mock_ctx.data = {}
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "No events" in str(exc_info.value)

    def test_raises_on_non_dict_event(self):
        """Test that ValidateEvents raises BusinessException for non-dict events."""
        self.mock_ctx.data = {"events": ["not a dict", {"event_id": "1"}]}
        skill = ValidateEvents("validate_events", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)
        assert "is not an object" in str(exc_info.value)
