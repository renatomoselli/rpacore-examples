"""Unit tests for the EnrichRecord skill."""

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from skills.enrich_record import EnrichRecord


class TestEnrichRecord:
    """Test the EnrichRecord skill."""

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

        skill = EnrichRecord("enrich_record", 3)
        skill.execute(ctx)

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

        skill = EnrichRecord("enrich_record", 3)
        skill.execute(ctx)

        assert ctx.state["enriched_record"]["userCity"] == ""

    def test_raises_on_missing_post(self):
        """Test that EnrichRecord raises SystemException when no current_post exists."""
        transaction = Transaction(
            reference="test",
            state={"current_user": {"id": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)

        assert "Missing required state" in str(exc_info.value)

    def test_raises_on_missing_user(self):
        """Test that EnrichRecord raises SystemException when no current_user exists."""
        transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1}},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)

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

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "missing required field: id" in str(exc_info.value)
        assert exc_info.value.stops_execution is True

    def test_raises_on_empty_user_name(self):
        """Test that EnrichRecord raises when user name is empty."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "", "email": "test@test.com"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "missing required field: name" in str(exc_info.value)
        assert exc_info.value.stops_execution is True

    def test_raises_on_missing_user_email(self):
        """Test that EnrichRecord raises when user email is missing."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "Test"}
        transaction = Transaction(
            reference="test",
            state={"current_post": post, "current_user": user},
        )
        ctx = ProcessContext(transaction=transaction)

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(ctx)

        assert "missing required field: email" in str(exc_info.value)
        assert exc_info.value.stops_execution is True
