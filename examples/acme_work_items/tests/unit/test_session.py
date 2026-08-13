from __future__ import annotations

import hashlib

import pytest
from rpacore import ProcessContext, SystemException, Transaction

from steps._session import (
    BrowserSession,
    RemoteWorkItem,
    compute_identity_hash,
    require_authenticated_session,
    validate_work_item_id,
)
from tests.conftest import FakeCredentials


class RecordingSession(BrowserSession):
    def __init__(self) -> None:
        self.credentials = None

    def ensure_authenticated(self, credentials) -> None:
        self.credentials = credentials


class _LocatorStub:
    def __init__(self, count: int = 0) -> None:
        self._count = count

    def count(self) -> int:
        return self._count

    def all(self) -> list[object]:
        return []


class _UnexpectedAuthPage:
    def __init__(self, url: str) -> None:
        self.url = url

    def goto(self, url: str, *, wait_until: str) -> None:
        return None

    def locator(self, selector: str) -> _LocatorStub:
        return _LocatorStub()


class _DialogStub:
    def __init__(self) -> None:
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True


class _ResponseStub:
    def __init__(self, url: str, *, ok: bool = True) -> None:
        self.url = url
        self.ok = ok


class _ResponseContextStub:
    def __init__(self, response: _ResponseStub) -> None:
        self.value = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


class _FormLocatorStub:
    def __init__(self, page, selector: str) -> None:
        self.page = page
        self.selector = selector

    def fill(self, value: str) -> None:
        self.page.values[self.selector] = value

    def select_option(self, value: str) -> None:
        self.page.values[self.selector] = value

    def click(self) -> None:
        self.page.clicked = self.selector
        if self.page.dialog_callback is not None:
            self.page.dialog_callback(self.page.dialog)

    def inner_text(self) -> str:
        return f"Comments: {self.page.stored_comment}"

    def count(self) -> int:
        return 0


class _RealUpdatePageStub:
    def __init__(self, stored_comment: str) -> None:
        self.url = "https://example.test/work-items/1001"
        self.stored_comment = stored_comment
        self.values: dict[str, str] = {}
        self.clicked = ""
        self.dialog = _DialogStub()
        self.dialog_callback = None
        self.visited: list[str] = []

    def goto(self, url: str, *, wait_until: str) -> None:
        self.url = url
        self.visited.append(url)

    def locator(self, selector: str) -> _FormLocatorStub:
        return _FormLocatorStub(self, selector)

    def once(self, event: str, callback) -> None:
        assert event == "dialog"
        self.dialog_callback = callback

    def expect_response(self, predicate) -> _ResponseContextStub:
        response = _ResponseStub("https://example.test/work-items/edit/1001")
        assert predicate(response)
        return _ResponseContextStub(response)


class _PaginationLinkStub:
    def __init__(self, text: str, href: str) -> None:
        self.text = text
        self.href = href

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str:
        assert name == "href"
        return self.href


class _PaginationLocatorStub:
    def __init__(self, links: list[_PaginationLinkStub] | None = None) -> None:
        self.links = links or []

    def count(self) -> int:
        return 0

    def all(self) -> list[_PaginationLinkStub]:
        return self.links


class _PaginationPageStub:
    def __init__(self, url: str, next_href: str) -> None:
        self.url = url
        self.next_href = next_href

    def goto(self, url: str, *, wait_until: str) -> None:
        self.url = url

    def locator(self, selector: str) -> _PaginationLocatorStub:
        if selector == "nav.woocommerce-pagination a.page-numbers":
            return _PaginationLocatorStub([_PaginationLinkStub("Next", self.next_href)])
        return _PaginationLocatorStub()


def test_validate_work_item_id_rejects_navigation_input() -> None:
    assert validate_work_item_id("WI-123_alpha") == "WI-123_alpha"
    for value in ("", "../admin", "item/1", " space", "a" * 129):
        with pytest.raises(ValueError):
            validate_work_item_id(value)


def test_real_site_type_descriptions_map_to_business_codes() -> None:
    assert BrowserSession._type_code("Verify Account Position") == "WI1"
    assert BrowserSession._type_code("Verify Account Positions") == "WI1"
    assert BrowserSession._type_code("Research Client Check Copy") == "WI2"
    assert BrowserSession._type_code("Process Vendor Invoice") == "WI3"
    assert BrowserSession._type_code("Generate Yearly Report for Vendor") == "WI4"
    assert BrowserSession._type_code("Calculate Client Security Hash") == "WI5"

    with pytest.raises(ValueError, match="Unknown work item type"):
        BrowserSession._type_code("Invent New Workflow")


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

    assert item.identity_hash == compute_identity_hash("C123", "WI456")
    assert item.fingerprint == hashlib.sha256(b"WI456|open|2026-06-23").hexdigest()
    assert item.stored_comment is None


def test_real_item_parser_maps_completed_to_closed() -> None:
    item = BrowserSession._parse_real_item_text(
        "\n".join(
            (
                "Client ID: C123",
                "WIID: WI456",
                "Type: Calculate Client Security Hash",
                "Status: Completed",
                "Date: 2026-06-23",
            )
        ),
        "1001",
    )

    assert item.status == "closed"
    assert item.fingerprint == hashlib.sha256(b"WI456|closed|2026-06-23").hexdigest()


def test_real_item_parser_rejects_missing_date() -> None:
    with pytest.raises(ValueError, match="Date"):
        BrowserSession._parse_real_item_text(
            "\n".join(
                (
                    "Client ID: C123",
                    "WIID: WI456",
                    "Type: Calculate Client Security Hash",
                    "Status: Open",
                )
            ),
            "1001",
        )


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


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("https://example.test/mfa", "unsupported authentication page"),
        ("https://example.test/login", "supported login form"),
    ],
)
def test_authentication_rejects_unexpected_page_shapes(monkeypatch, url, message) -> None:
    session = BrowserSession("https://example.test")
    page = _UnexpectedAuthPage(url)
    monkeypatch.setattr(session, "_healthy_page", lambda: page)

    with pytest.raises(SystemException, match=message):
        session.ensure_authenticated(FakeCredentials())


@pytest.mark.parametrize(
    ("method_name", "submitted_status", "returned_status"),
    [
        ("_apply_hash_via_update_form", "Open", "open"),
        ("_close_via_update_form", "Completed", "closed"),
    ],
)
def test_real_update_form_paths_submit_and_verify_remote_comment(
    monkeypatch,
    method_name,
    submitted_status,
    returned_status,
) -> None:
    session = BrowserSession("https://example.test")
    page = _RealUpdatePageStub("desired")
    remote = RemoteWorkItem(
        "1001",
        "C",
        "WI",
        "WI5",
        returned_status,
        "desired",
        "fingerprint",
    )
    monkeypatch.setattr(session, "_read_item", lambda current_page, work_item_id: remote)

    result = getattr(session, method_name)(
        page,
        "1001",
        security_hash="desired",
    )

    assert page.values == {"#newComment": "desired", "#newStatus": submitted_status}
    assert page.clicked == "#buttonUpdate"
    assert page.dialog.accepted is True
    assert result.stored_comment == "desired"
    assert page.visited[-1].endswith("/work-items/1001")


def test_real_update_form_rejects_mismatched_remote_comment() -> None:
    session = BrowserSession("https://example.test")
    page = _RealUpdatePageStub("different")

    with pytest.raises(SystemException, match="was not stored"):
        session._submit_update_form(
            page,
            "1001",
            security_hash="desired",
            status="Open",
            action="update_work_item",
        )


@pytest.mark.parametrize(
    "next_href",
    [
        "https://evil.test/work-items?page=2",
        "https://example.test/admin",
        "https://user:secret@example.test/work-items",
        "ftp://example.test/work-items",
    ],
)
def test_pagination_rejects_urls_outside_expected_work_items_page(next_href) -> None:
    session = BrowserSession("https://example.test")
    page = _PaginationPageStub("https://example.test/work-items", next_href)

    with pytest.raises(ValueError, match="pagination URL"):
        session._next_work_items_page(page)


def test_pagination_loop_detection_is_reported(monkeypatch) -> None:
    session = BrowserSession("https://example.test")
    page = _PaginationPageStub("https://example.test/work-items", "/work-items")
    monkeypatch.setattr(session, "_page_or_raise", lambda: page)

    with pytest.raises(SystemException, match="Unable to discover") as exc_info:
        session.discover_open_items()

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "pagination loop" in str(exc_info.value.__cause__)
