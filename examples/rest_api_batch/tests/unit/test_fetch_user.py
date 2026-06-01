"""Unit tests for the FetchUser skill."""

from unittest.mock import Mock, patch

import pytest

from rpacore import SystemException
from skills.fetch_user import FetchUser


class TestFetchUser:
    """Test the FetchUser skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_tx = Mock()
        self.mock_ctx = Mock()
        self.mock_ctx.data = {"current_post": {"id": 1, "userId": 1}}
        self.mock_ctx.config = {}

    @patch("skills.fetch_user.requests.get")
    def test_fetches_user_by_id(self, mock_get):
        """Test that FetchUser retrieves the correct user."""
        sample_user = {
            "id": 1,
            "name": "Leanne Graham",
            "email": "Sincere@april.biz",
            "address": {"city": "Gwenborough"},
        }
        mock_response = Mock()
        mock_response.json.return_value = sample_user
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        skill = FetchUser("fetch_user", 1)
        skill.execute(self.mock_ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/users/1", timeout=30
        )
        assert self.mock_ctx.data["current_user"] == sample_user

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_missing_post(self, mock_get):
        """Test that FetchUser raises SystemException when no current_post exists."""
        self.mock_ctx.data = {}  # No current_post

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "No current_post" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_missing_user_id(self, mock_get):
        """Test that FetchUser raises SystemException when post has no userId."""
        self.mock_ctx.data = {"current_post": {"id": 1}}  # No userId

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "no userId" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_http_error(self, mock_get):
        """Test that FetchUser raises SystemException on HTTP error."""
        import requests as requests_lib

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        http_exc = requests_lib.exceptions.HTTPError(response=mock_response)
        mock_get.side_effect = http_exc

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "HTTP error" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchUser raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchUser raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchUser raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Error fetching user" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchUser raises SystemException when response is not valid JSON."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = mock_response

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Invalid JSON" in str(exc_info.value)
