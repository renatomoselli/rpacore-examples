"""Unit tests for the ValidatePost skill."""

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from skills.validate_post import ValidatePost


class TestValidatePost:
    """Test the ValidatePost skill."""

    def test_passes_for_valid_post(self):
        """Test that ValidatePost passes for a post with non-empty title and body."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "title": "Hello", "body": "World", "userId": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)
        skill.execute(ctx)  # Should not raise

    def test_raises_on_empty_title(self):
        """Test that ValidatePost raises BusinessException for empty title."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "title": "", "body": "World", "userId": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "empty or missing title" in str(exc_info.value)

    def test_raises_on_empty_body(self):
        """Test that ValidatePost raises BusinessException for empty body."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "title": "Hello", "body": "", "userId": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "empty or missing body" in str(exc_info.value)

    def test_raises_on_whitespace_only_title(self):
        """Test that ValidatePost raises for whitespace-only title."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "title": "   ", "body": "World", "userId": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "empty or missing title" in str(exc_info.value)

    def test_raises_on_missing_context(self):
        """Test that ValidatePost raises SystemException when no current_post exists."""
        transaction = Transaction(reference="test", state={})
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)

        assert "Missing required state" in str(exc_info.value)

    def test_raises_on_missing_user_id(self):
        """Test that ValidatePost raises BusinessException when userId is missing."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "title": "Hello", "body": "World"}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = ValidatePost("validate_post", 2)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "missing userId" in str(exc_info.value)
        assert exc_info.value.stops_execution is True
