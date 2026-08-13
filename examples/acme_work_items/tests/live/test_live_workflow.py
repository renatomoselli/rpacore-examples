from __future__ import annotations

import os

import pytest
from rpacore import EnvCredentialProvider

from steps._session import BrowserSession


pytestmark = pytest.mark.live


def test_live_login_and_discovery_are_opt_in() -> None:
    if os.environ.get("RUN_ACME_LIVE") != "1":
        pytest.skip("set RUN_ACME_LIVE=1 to exercise the external ACME site")
    provider = EnvCredentialProvider()
    with BrowserSession("https://acme-test.uipath.com", headless=True) as resources:
        session = resources["browser_session"]
        assert isinstance(session, BrowserSession)
        session.ensure_authenticated(provider)
        assert isinstance(session.discover_open_items(), list)
