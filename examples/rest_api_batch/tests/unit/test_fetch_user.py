"""Unit tests for the FetchUser skill."""

from unittest.mock import patch

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from skills.fetch_user import FetchUser


class TestFetchUser:
    """Test the FetchUser skill."""

    def setup_method(self):
        """Set up test fixtures with real Transaction/ProcessContext."""
        self.transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "userId": 1}},
        )
        self.ctx = ProcessContext(transaction=self.transaction, config={})

    def test_fixture_mode_uses_deterministic_user_without_http(self):
        self.ctx.config["api_mode"] = "fixture"

        with patch("skills.fetch_user.requests.get") as mock_get:
            skill = FetchUser("fetch_user", 1)
            skill.execute(self.ctx)

        mock_get.assert_not_called()
        assert self.ctx.state["current_user"]["id"] == 1

    def test_fixture_mode_unknown_user_id_is_business_exception(self):
        self.ctx.config["api_mode"] = "fixture"
        self.transaction.state = {"current_post": {"id": 99, "userId": 999}}

        with patch("skills.fetch_user.requests.get") as mock_get:
            skill = FetchUser("fetch_user", 1)
            with pytest.raises(BusinessException) as exc_info:
                skill.execute(self.ctx)

        mock_get.assert_not_called()
        assert "unknown userId" in str(exc_info.value)
        assert exc_info.value.stops_execution is True

    @patch("skills.fetch_user.requests.get")
    def test_fetches_user_by_id(self, mock_get):
        """Test that FetchUser retrieves the correct user."""
        sample_user = {
            "id": 1,
            "name": "Leanne Graham",
            "email": "Sincere@april.biz",
            "address": {"city": "Gwenborough"},
        }
        mock_response = mock_get.return_value
        mock_response.json.return_value = sample_user
        mock_response.raise_for_status.return_value = None

        skill = FetchUser("fetch_user", 1)
        skill.execute(self.ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/users/1", timeout=30
        )
        assert self.ctx.state["current_user"] == sample_user

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_missing_post(self, mock_get):
        """Test that FetchUser raises SystemException when no current_post exists."""
        self.transaction.state = {}

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Missing required state" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_business_exception_on_missing_user_id(self, mock_get):
        """Test that FetchUser raises BusinessException when post has no userId."""
        self.transaction.state = {"current_post": {"id": 1}}  # No userId

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(BusinessException) as exc_info:
            skill.execute(self.ctx)

        assert "no userId" in str(exc_info.value)
        assert exc_info.value.stops_execution is True

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_http_error(self, mock_get):
        """Test that FetchUser raises SystemException on HTTP error."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(response=mock_response)

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "HTTP error" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchUser raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchUser raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchUser raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Error fetching user" in str(exc_info.value)

    @patch("skills.fetch_user.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchUser raises SystemException when response is not valid JSON."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")

        skill = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.ctx)

        assert "Invalid JSON" in str(exc_info.value)
