"""Unit tests for the EnrichRecord skill."""

from unittest.mock import Mock

from skills.enrich_record import EnrichRecord


class TestEnrichRecord:
    """Test the EnrichRecord skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}

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
        self.mock_ctx.data = {
            "current_post": post,
            "current_user": user,
        }

        skill = EnrichRecord("enrich_record", 3)
        skill.execute(self.mock_ctx)

        expected = {
            "postId": 1,
            "title": "Test Post",
            "body": "Test body content",
            "userId": 1,
            "userName": "Leanne Graham",
            "userEmail": "Sincere@april.biz",
            "userCity": "Gwenborough",
        }
        assert self.mock_ctx.data["enriched_record"] == expected

    def test_enriches_with_empty_city_when_missing(self):
        """Test that EnrichRecord handles missing city gracefully."""
        post = {"id": 1, "title": "Test", "body": "Test"}
        user = {"id": 1, "name": "Test", "email": "test@test.com"}
        self.mock_ctx.data = {"current_post": post, "current_user": user}

        skill = EnrichRecord("enrich_record", 3)
        skill.execute(self.mock_ctx)

        assert self.mock_ctx.data["enriched_record"]["userCity"] == ""

    def test_raises_on_missing_post(self):
        """Test that EnrichRecord raises when no current_post exists."""
        self.mock_ctx.data = {"current_user": {"id": 1}}

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(RuntimeError) as exc_info:
            skill.execute(self.mock_ctx)

        assert "No current_post" in str(exc_info.value)

    def test_raises_on_missing_user(self):
        """Test that EnrichRecord raises when no current_user exists."""
        self.mock_ctx.data = {"current_post": {"id": 1}}

        skill = EnrichRecord("enrich_record", 3)

        with pytest.raises(RuntimeError) as exc_info:
            skill.execute(self.mock_ctx)

        assert "No current_user" in str(exc_info.value)
