"""Unit tests for the FetchPosts skill."""

from unittest.mock import patch

import pytest

from rpacore import ProcessContext, SystemException, Transaction
from skills.fetch_posts import FetchPosts


class TestFetchPosts:
    """Test the FetchPosts skill."""

    def setup_method(self):
        """Set up test fixtures with real Transaction/ProcessContext."""
        self.transaction = Transaction(reference="test", state={})
        self.ctx = ProcessContext(transaction=self.transaction, config={})

    def test_fixture_mode_uses_deterministic_posts_without_http(self):
        self.ctx.config["api_mode"] = "fixture"

        with patch("skills.fetch_posts.requests.get") as mock_get:
            skill = FetchPosts("fetch_posts", 1)
            skill.execute(self.ctx)

        mock_get.assert_not_called()
        assert [post["id"] for post in self.ctx.state["posts"]] == [1, 2, 3]

    @patch("skills.fetch_posts.requests.get")
    def test_fetches_all_posts(self, mock_get):
        """Test that FetchPosts retrieves all posts from the API."""
        sample_posts = [
            {"id": 1, "title": "Post 1", "body": "Body 1", "userId": 1},
            {"id": 2, "title": "Post 2", "body": "Body 2", "userId": 2},
        ]
        mock_response = mock_get.return_value
        mock_response.json.return_value = sample_posts
        mock_response.raise_for_status.return_value = None

        skill = FetchPosts("fetch_posts", 1)
        skill.execute(self.ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts", timeout=30
        )
        assert self.ctx.state["posts"] == sample_posts

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_http_error(self, mock_get):
        """Test that FetchPosts raises SystemException on HTTP error."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(response=mock_response)

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "HTTP error" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchPosts raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchPosts raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchPosts raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Error fetching posts" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchPosts raises SystemException when response is not valid JSON."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Invalid JSON" in str(exc_info.value)
