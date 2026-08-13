from __future__ import annotations

"""Unit tests for the EnrichRecord step."""

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from steps.enrich_record import EnrichRecord


class TestEnrichRecord:
    """Test the EnrichRecord step."""

    def test_enriches_record_with_post_and_user(self):
        """Test that EnrichRecord merges post and user data correctly."""
        post = {
            "id": 1,
            "title": "Test Post",
            "body": "Test body content",
        }
        user = {
            "id": 1,
            "name": "Leanne Graham",
            "email": "Sincere@april.biz",
            "address": {"city": "Gwenborough"},
        }
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)
        step.execute(ctx)

        expected = {
            "postId": 1,
            "title": "Test Post",
            "body": "Test body content",
            "userId": 1,
            "userName": "Leanne Graham",
            "userEmail": "Sincere@april.biz",
            "userCity": "Gwenborough",
        }
        assert ctx.state["enriched_record"] == expected

    def test_enriches_with_empty_city_when_missing(self):
        """Test that EnrichRecord handles missing city gracefully."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "Test", "email": "test@test.com"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)
        step.execute(ctx)

        assert ctx.state["enriched_record"]["userCity"] == ""

    def test_raises_on_invalid_address_shape(self):
        """Test that malformed user address data fails as a technical error."""
        transaction = Transaction(
            reference="test",
            state={
                "current_post": {"id": 1, "title": "Test", "body": "Test"},
                "current_user": {
                    "id": 1,
                    "name": "Test",
                    "email": "test@test.com",
                    "address": "not-an-object",
                },
            },
        )
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(SystemException, match="invalid address data"):
            EnrichRecord("enrich_record", 3).execute(ctx)

        assert "enriched_record" not in ctx.state

    def test_raises_on_missing_post(self):
        """Test that EnrichRecord raises SystemException when no current_post exists."""
        transaction = Transaction(
            reference="test",
            state={"current_user": {"id": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)

        with pytest.raises(SystemException) as exc_info:
            step.execute(ctx)

        assert "Missing required state" in str(exc_info.value)

    def test_raises_on_missing_user(self):
        """Test that EnrichRecord raises SystemException when no current_user exists."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)

        with pytest.raises(SystemException) as exc_info:
            step.execute(ctx)

        assert "Missing required state" in str(exc_info.value)

    def test_raises_on_missing_user_id(self):
        """Test that EnrichRecord raises when user id is missing."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"name": "Test", "email": "test@test.com"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(ctx)

        assert "missing required field: id" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    def test_raises_on_zero_user_id(self):
        """Test that an enriched user id must be positive."""
        transaction = Transaction(
            reference="test",
            state={
                "current_post": {"id": 1, "title": "Test", "body": "Test"},
                "current_user": {"id": 0, "name": "Test", "email": "a@b.test"},
            },
        )
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(BusinessException, match="invalid or missing required field"):
            EnrichRecord("enrich_record", 3).execute(ctx)

    def test_raises_on_empty_user_name(self):
        """Test that EnrichRecord raises when user name is empty."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "", "email": "test@test.com"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(ctx)

        assert "missing required field: name" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @pytest.mark.parametrize("name", ["   ", 123])
    def test_raises_on_invalid_user_name(self, name):
        """Test that a user name must be a nonblank string."""
        transaction = Transaction(
            reference="test",
            state={
                "current_post": {"id": 1, "title": "Test", "body": "Test"},
                "current_user": {
                    "id": 1,
                    "name": name,
                    "email": "test@test.com",
                },
            },
        )
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(BusinessException, match="missing required field: name"):
            EnrichRecord("enrich_record", 3).execute(ctx)

    def test_raises_on_missing_user_email(self):
        """Test that EnrichRecord raises when user email is missing."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "Test"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        step = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(ctx)

        assert "missing required field: email" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @pytest.mark.parametrize("email", ["   ", 123])
    def test_raises_on_invalid_user_email(self, email):
        """Test that a user email must be a nonblank string."""
        transaction = Transaction(
            reference="test",
            state={
                "current_post": {"id": 1, "title": "Test", "body": "Test"},
                "current_user": {"id": 1, "name": "Test", "email": email},
            },
        )
        ctx = ProcessContext(transaction=transaction)

        with pytest.raises(BusinessException, match="missing required field: email"):
            EnrichRecord("enrich_record", 3).execute(ctx)
