from __future__ import annotations

"""Unit tests for the FetchPosts step."""

from unittest.mock import patch

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from steps.fetch_posts import FetchPosts


class TestFetchPosts:
    """Test the FetchPosts step."""

    def setup_method(self):
        """Set up test fixtures with real Transaction/ProcessContext."""
        self.transaction = Transaction(reference="test", state={})
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={"api_mode": "live"},
        )

    def test_fixture_mode_uses_deterministic_posts_without_http(self):
        self.ctx.config["api_mode"] = "fixture"

        with patch("steps.fetch_posts.requests.get") as mock_get:
            step = FetchPosts("fetch_posts", 1)
            step.execute(self.ctx)

        mock_get.assert_not_called()
        assert [post["id"] for post in self.ctx.state["posts"]] == [1, 2, 3]

    @patch("steps.fetch_posts.requests.get")
    def test_fetches_all_posts(self, mock_get):
        """Test that FetchPosts retrieves all posts from the API."""
        sample_posts = [
            {"id": 1, "title": "Post 1", "body": "Body 1", "userId": 1},
            {"id": 2, "title": "Post 2", "body": "Body 2", "userId": 2},
        ]
        mock_response = mock_get.return_value
        mock_response.json.return_value = sample_posts
        mock_response.raise_for_status.return_value = None

        step = FetchPosts("fetch_posts", 1)
        step.execute(self.ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/posts", timeout=30
        )
        assert self.ctx.state["posts"] == sample_posts

    @patch("steps.fetch_posts.requests.get")
    def test_raises_business_exception_on_http_404(self, mock_get):
        """Test that a permanent setup response is not retried."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(response=mock_response)

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)

        assert "posts request was rejected: 404" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @pytest.mark.parametrize("status_code", [408, 429, 500])
    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_retryable_http_error(
        self, mock_get, status_code
    ):
        """Test that transient setup responses retain retry semantics."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = status_code
        mock_response.reason = "Temporary failure"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(
            response=mock_response
        )

        with pytest.raises(SystemException, match="HTTP error fetching posts"):
            FetchPosts("fetch_posts", 1).execute(self.ctx)

    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchPosts raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchPosts raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchPosts raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Error fetching posts" in str(exc_info.value)

    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchPosts raises SystemException when response is not valid JSON."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Invalid JSON" in str(exc_info.value)

    @patch("steps.fetch_posts.requests.get")
    def test_raises_system_exception_on_invalid_response_shape(self, mock_get):
        """Test that valid JSON must still contain a list of post objects."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [{"id": 1}, "not-an-object"]

        step = FetchPosts("fetch_posts", 1)

        with pytest.raises(SystemException, match="JSON array of objects"):
            step.execute(self.ctx)

        assert "posts" not in self.ctx.state

    @pytest.mark.parametrize("config", [{}, {"api_mode": "unexpected"}])
    @patch("steps.fetch_posts.requests.get")
    def test_rejects_missing_or_invalid_api_mode(self, mock_get, config):
        """Test that invalid configuration cannot silently enable live HTTP."""
        ctx = ProcessContext(transaction=self.transaction, config=config)

        with pytest.raises(SystemException):
            FetchPosts("fetch_posts", 1).execute(ctx)

        mock_get.assert_not_called()
