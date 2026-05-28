"""Unit tests for the FetchPosts skill."""

from unittest.mock import Mock, patch

import pytest

from oref import SystemException
from skills.fetch_posts import FetchPosts


class TestFetchPosts:
    """Test the FetchPosts skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_tx = Mock()
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}
        self.mock_ctx.config = {}

    @patch("skills.fetch_posts.requests.get")
    def test_fetches_all_posts(self, mock_get):
        """Test that FetchPosts retrieves all posts from the API."""
        sample_posts = [
            {"id": 1, "title": "Post 1", "body": "Body 1", "userId": 1},
            {"id": 2, "title": "Post 2", "body": "Body 2", "userId": 2},
        ]
        mock_response = Mock()
        mock_response.json.return_value = sample_posts
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        skill = FetchPosts("fetch_posts", 1)
        skill.execute(self.mock_ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts", timeout=30
        )
        assert self.mock_ctx.data["posts"] == sample_posts

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_http_error(self, mock_get):
        """Test that FetchPosts raises SystemException on HTTP error."""
        import requests as requests_lib

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        http_exc = requests_lib.exceptions.HTTPError(response=mock_response)
        mock_get.side_effect = http_exc

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "HTTP error" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchPosts raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchPosts raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchPosts raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Error fetching posts" in str(exc_info.value)

    @patch("skills.fetch_posts.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchPosts raises SystemException when response is not valid JSON."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = mock_response

        skill = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Invalid JSON" in str(exc_info.value)
