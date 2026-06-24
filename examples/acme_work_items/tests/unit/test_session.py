from __future__ import annotations

import hashlib

import pytest
from rpacore import ProcessContext, SystemException, Transaction

from skills._session import BrowserSession, require_authenticated_session, validate_work_item_id
from tests.conftest import FakeCredentials


class RecordingSession(BrowserSession):
    def __init__(self) -> None:
        self.credentials = None

    def ensure_authenticated(self, credentials) -> None:
        self.credentials = credentials


def test_validate_work_item_id_rejects_navigation_input() -> None:
    assert validate_work_item_id("WI-123_alpha") == "WI-123_alpha"
    for value in ("", "../admin", "item/1", " space", "a" * 129):
        with pytest.raises(ValueError):
            validate_work_item_id(value)


def test_real_site_type_descriptions_map_to_business_codes() -> None:
    assert BrowserSession._type_code("Verify Account Position") == "WI1"
    assert BrowserSession._type_code("Research Client Check Copy") == "WI2"
    assert BrowserSession._type_code("Process Vendor Invoice") == "WI3"
    assert BrowserSession._type_code("Generate Yearly Report for Vendor") == "WI4"
    assert BrowserSession._type_code("Calculate Client Security Hash") == "WI5"


def test_real_item_parser_uses_documented_hash_formulas() -> None:
    item = BrowserSession._parse_real_item_text(
        "\n".join(
            (
                "Client ID: C123",
                "WIID: WI456",
                "Type: Calculate Client Security Hash",
                "Status: Open",
                "Date: 2026-06-23",
            )
        ),
        "1001",
    )

    assert item.identity_hash == hashlib.sha1(b"C123WI456").hexdigest()
    assert item.fingerprint == hashlib.sha256(b"WI456|open|2026-06-23").hexdigest()
    assert item.stored_comment is None


def test_require_authenticated_session_uses_context_credentials() -> None:
    credentials = FakeCredentials()
    session = RecordingSession()
    ctx = ProcessContext(
        transaction=Transaction(reference="session"),
        resources={"browser_session": session},
        credentials=credentials,
    )

    assert require_authenticated_session(ctx) is session
    assert session.credentials is credentials


def test_require_authenticated_session_rejects_missing_resource() -> None:
    ctx = ProcessContext(transaction=Transaction(reference="session"))
    with pytest.raises(SystemException, match="missing or invalid"):
        require_authenticated_session(ctx)
