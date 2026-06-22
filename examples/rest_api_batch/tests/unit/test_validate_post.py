from __future__ import annotations

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

    @pytest.mark.parametrize("field", ["title", "body"])
    def test_raises_on_non_string_text_field(self, field):
        """Test that title and body must be strings rather than coerced values."""
        post = {"id": 1, "title": "Hello", "body": "World", "userId": 1}
        post[field] = 123
        transaction = Transaction(reference="test", state={"current_post": post})
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(BusinessException, match=f"empty or missing {field}"):
            ValidatePost("validate_post", 2).execute(ctx)

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

    @pytest.mark.parametrize("user_id", [0, -1, "1", True])
    def test_raises_on_invalid_user_id(self, user_id):
        """Test that userId must be a positive integer."""
        transaction = Transaction(
            reference="test",
            state={
                "current_post": {
                    "id": 1,
                    "title": "Hello",
                    "body": "World",
                    "userId": user_id,
                }
            },
        )
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(BusinessException, match="invalid or missing userId"):
            ValidatePost("validate_post", 2).execute(ctx)
