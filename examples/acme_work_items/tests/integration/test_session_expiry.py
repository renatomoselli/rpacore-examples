from __future__ import annotations

import pytest
from rpacore import SystemException

from main import run_example
from steps._session import BrowserSession
from tests.conftest import FakeCredentials


pytestmark = pytest.mark.integration


class ExpireAfterFetchSession(BrowserSession):
    def __init__(self, config, expire) -> None:
        super().__init__(
            str(config["base_url"]),
            headless=True,
            page_load_timeout_ms=int(config["page_load_timeout_ms"]),
            action_timeout_ms=int(config["action_timeout_ms"]),
        )
        self.expire = expire
        self.expired = False

    def fetch_item(self, work_item_id: str):
        item = super().fetch_item(work_item_id)
        if not self.expired:
            self.expired = True
            self.expire()
        return item


def test_expired_cookie_is_reauthenticated_before_update(
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")

    def factory(config):
        return ExpireAfterFetchSession(config, acme_server.state.expire_sessions)

    result = run_example(example_config, credentials=credentials, session_factory=factory)
    assert result.queue_summary.completed == 1
    assert acme_server.state.update_counts["1001"] == 1
    assert acme_server.state.close_counts["1001"] == 1


@pytest.mark.parametrize("resource_name", ["_page", "_context", "_browser"])
def test_closed_browser_resource_is_rebuilt_and_cleanup_releases_resources(
    resource_name,
    example_config,
    acme_server,
    credentials,
) -> None:
    session = BrowserSession(
        acme_server.base_url,
        headless=True,
        page_load_timeout_ms=10000,
        action_timeout_ms=5000,
    )
    with session:
        session.ensure_authenticated(credentials)
        original_page = session._page
        assert original_page is not None
        resource = getattr(session, resource_name)
        assert resource is not None
        resource.close()
        session.ensure_authenticated(credentials)
        assert session._page is not original_page
        assert session._page is not None and not session._page.is_closed()
    assert session._page is None
    assert session._context is None
    assert session._browser is None
    assert session._playwright is None


def test_rejected_credentials_do_not_appear_in_error(
    example_config,
    acme_server,
) -> None:
    credentials = FakeCredentials(username="secret-user", password="secret-password")
    with BrowserSession(acme_server.base_url, headless=True) as resources:
        session = resources["browser_session"]
        with pytest.raises(SystemException) as captured:
            session.ensure_authenticated(credentials)
    assert "secret-user" not in str(captured.value)
    assert "secret-password" not in str(captured.value)


def test_missing_credential_names_the_key_without_a_secret(
    example_config,
    acme_server,
) -> None:
    credentials = FakeCredentials()
    del credentials.values["acme_password"]
    with BrowserSession(acme_server.base_url, headless=True) as resources:
        session = resources["browser_session"]
        with pytest.raises(SystemException, match="acme_password"):
            session.ensure_authenticated(credentials)
