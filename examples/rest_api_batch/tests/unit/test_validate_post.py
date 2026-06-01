"""Unit tests for the ValidatePost skill."""

from unittest.mock import Mock

import pytest

from rpacore import BusinessException, SystemException
from skills.validate_post import ValidatePost


class TestValidatePost:
    """Test the ValidatePost skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

    def test_passes_for_valid_post(self):
        """Test that ValidatePost passes for a post with non-empty title and body."""
        self.mock_ctx.data = {
            "current_post": {"id": 1, "title": "Hello", "body": "World"}
        }

        skill = ValidatePost("validate_post", 2)
        skill.execute(self.mock_ctx)  # Should not raise

    def test_raises_on_empty_title(self):
        """Test that ValidatePost raises BusinessException for empty title."""
        self.mock_ctx.data = {
            "current_post": {"id": 1, "title": "", "body": "World"}
        }

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "empty or missing title" in str(exc_info.value)

    def test_raises_on_empty_body(self):
        """Test that ValidatePost raises BusinessException for empty body."""
        self.mock_ctx.data = {
            "current_post": {"id": 1, "title": "Hello", "body": ""}
        }

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "empty or missing body" in str(exc_info.value)

    def test_raises_on_whitespace_only_title(self):
        """Test that ValidatePost raises for whitespace-only title."""
        self.mock_ctx.data = {
            "current_post": {"id": 1, "title": "   ", "body": "World"}
        }

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "empty or missing title" in str(exc_info.value)

    def test_raises_on_missing_context(self):
        """Test that ValidatePost raises SystemException when no current_post exists."""
        self.mock_ctx.data = {}

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "No current_post" in str(exc_info.value)
