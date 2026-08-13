from __future__ import annotations

"""Unit tests for the FetchUser step."""

from unittest.mock import patch

import pytest

from rpacore import BusinessException, ProcessContext, SystemException, Transaction
from steps.fetch_user import FetchUser


class TestFetchUser:
    """Test the FetchUser step."""

    def setup_method(self):
        """Set up test fixtures with real Transaction/ProcessContext."""
        self.transaction = Transaction(
            reference="test",
            state={"current_post": {"id": 1, "userId": 1}},
        )
        self.ctx = ProcessContext(
            transaction=self.transaction,
            config={"api_mode": "live"},
        )

    def test_fixture_mode_uses_deterministic_user_without_http(self):
        self.ctx.config["api_mode"] = "fixture"

        with patch("steps.fetch_user.requests.get") as mock_get:
            step = FetchUser("fetch_user", 1)
            step.execute(self.ctx)

        mock_get.assert_not_called()
        assert self.ctx.state["current_user"]["id"] == 1

    def test_fixture_mode_unknown_user_id_is_business_exception(self):
        self.ctx.config["api_mode"] = "fixture"
        self.transaction.state = {"current_post": {"id": 99, "userId": 999}}

        with patch("steps.fetch_user.requests.get") as mock_get:
            step = FetchUser("fetch_user", 1)
            with pytest.raises(BusinessException) as exc_info:
                step.execute(self.ctx)

        mock_get.assert_not_called()
        assert "unknown userId" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @patch("steps.fetch_user.requests.get")
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

        step = FetchUser("fetch_user", 1)
        step.execute(self.ctx)

        mock_get.assert_called_once_with(
            "https://jsonplaceholder.typicode.com/users/1", timeout=30
        )
        assert self.ctx.state["current_user"] == sample_user

    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_missing_post(self, mock_get):
        """Test that FetchUser raises SystemException when no current_post exists."""
        self.transaction.state = {}

        step = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Missing required state" in str(exc_info.value)

    @patch("steps.fetch_user.requests.get")
    def test_raises_business_exception_on_missing_user_id(self, mock_get):
        """Test that FetchUser raises BusinessException when post has no userId."""
        self.transaction.state = {"current_post": {"id": 1}}  # No userId

        step = FetchUser("fetch_user", 1)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)

        assert "no userId" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @patch("steps.fetch_user.requests.get")
    def test_raises_business_exception_on_zero_user_id(self, mock_get):
        """Test that zero is not accepted as a domain user identifier."""
        self.transaction.state = {"current_post": {"id": 1, "userId": 0}}

        with pytest.raises(BusinessException, match="invalid or no userId"):
            FetchUser("fetch_user", 1).execute(self.ctx)

        mock_get.assert_not_called()

    @patch("steps.fetch_user.requests.get")
    def test_raises_business_exception_on_http_404(self, mock_get):
        """Test that a permanent not-found response is not retried."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(response=mock_response)

        step = FetchUser("fetch_user", 1)

        with pytest.raises(BusinessException) as exc_info:
            step.execute(self.ctx)

        assert "request was rejected: 404" in str(exc_info.value)
        assert exc_info.value.halts_remaining_steps is True

    @pytest.mark.parametrize("status_code", [408, 429, 500])
    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_retryable_http_error(
        self, mock_get, status_code
    ):
        """Test that transient HTTP responses retain retry semantics."""
        import requests as requests_lib

        mock_response = mock_get.return_value
        mock_response.status_code = status_code
        mock_response.reason = "Temporary failure"
        mock_get.side_effect = requests_lib.exceptions.HTTPError(
            response=mock_response
        )

        with pytest.raises(SystemException, match="HTTP error fetching user"):
            FetchUser("fetch_user", 1).execute(self.ctx)

    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_connection_error(self, mock_get):
        """Test that FetchUser raises SystemException on connection error."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.ConnectionError("Connection refused")

        step = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Connection error" in str(exc_info.value)

    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_timeout(self, mock_get):
        """Test that FetchUser raises SystemException on timeout."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.Timeout("Read timed out")

        step = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Timeout" in str(exc_info.value)

    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_generic_request_error(self, mock_get):
        """Test that FetchUser raises SystemException on generic RequestException."""
        import requests as requests_lib

        mock_get.side_effect = requests_lib.exceptions.RequestException("Something went wrong")

        step = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Error fetching user" in str(exc_info.value)

    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_invalid_json(self, mock_get):
        """Test that FetchUser raises SystemException when response is not valid JSON."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")

        step = FetchUser("fetch_user", 1)

        with pytest.raises(SystemException) as exc_info:
            step.execute(self.ctx)

        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.parametrize(
        "payload",
        [[], {}, {"id": 1, "name": "Name"}, {"id": 0, "name": "Name", "email": "a@b.test"}],
    )
    @patch("steps.fetch_user.requests.get")
    def test_raises_system_exception_on_invalid_user_payload(
        self, mock_get, payload
    ):
        """Test that malformed successful responses fail at the API boundary."""
        mock_response = mock_get.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = payload

        with pytest.raises(SystemException, match="Invalid user 1 response"):
            FetchUser("fetch_user", 1).execute(self.ctx)

        assert "current_user" not in self.ctx.state

    @pytest.mark.parametrize("config", [{}, {"api_mode": "unexpected"}])
    @patch("steps.fetch_user.requests.get")
    def test_rejects_missing_or_invalid_api_mode(self, mock_get, config):
        """Test that invalid configuration cannot silently enable live HTTP."""
        ctx = ProcessContext(transaction=self.transaction, config=config)

        with pytest.raises(SystemException):
            FetchUser("fetch_user", 1).execute(ctx)

        mock_get.assert_not_called()
