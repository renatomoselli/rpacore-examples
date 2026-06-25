from __future__ import annotations

import hashlib
import re
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, urljoin, urlparse

from rpacore import (
    CredentialNotFoundError,
    CredentialProvider,
    ProcessContext,
    SystemException,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright


_WORK_ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_TYPE_DESCRIPTION_TO_CODE: dict[str, str] = {
    "calculate client security hash": "WI5",
    "verify account position": "WI1",
    "verify account positions": "WI1",
    "research client check copy": "WI2",
    "process vendor invoice": "WI3",
    "generate yearly report for vendor": "WI4",
}


@dataclass(frozen=True)
class DiscoveredItem:
    work_item_id: str
    discovered_hash: str


@dataclass(frozen=True)
class RemoteWorkItem:
    work_item_id: str
    client_id: str
    wiid: str
    item_type: str
    status: str
    identity_hash: str
    fingerprint: str
    # Real detail pages do not expose comments. This is populated only from a
    # directly read fake value or after exact real-form verification succeeds.
    stored_comment: str | None = None
    was_already_closed: bool = False


class RemoteConflictError(Exception):
    """The remote item no longer satisfies an expected business precondition."""


def compute_identity_hash(client_id: str, wiid: str) -> str:
    """Return the ACME WI5 security hash for one immutable identity pair."""
    return hashlib.sha1(f"{client_id}{wiid}".encode("utf-8")).hexdigest()


def validate_work_item_id(work_item_id: str) -> str:
    if not isinstance(work_item_id, str) or not _WORK_ITEM_ID.fullmatch(work_item_id):
        raise ValueError("work_item_id must contain only letters, numbers, '_' or '-'")
    return work_item_id


class BrowserSession(AbstractContextManager[dict[str, object]]):
    """Own a repairable Playwright browser session without retaining secrets."""

    def __init__(
        self,
        base_url: str,
        *,
        headless: bool = True,
        page_load_timeout_ms: int = 30000,
        action_timeout_ms: int = 10000,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain embedded credentials")
        self.base_url = base_url.rstrip("/") + "/"
        self.headless = headless
        self.page_load_timeout_ms = page_load_timeout_ms
        self.action_timeout_ms = action_timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> dict[str, object]:
        self._start()
        return {"browser_session": self}

    def __exit__(self, exc_type, exc, traceback) -> bool:
        cleanup_error = self._close_resources()
        if cleanup_error is not None and exc is None:
            raise SystemException(
                "Browser resources could not be closed cleanly",
                action="browser_cleanup",
            ) from cleanup_error
        return False

    def ensure_authenticated(self, credentials: CredentialProvider) -> None:
        """Probe browser and login state, repairing either when necessary."""
        try:
            page = self._healthy_page()
            page.goto(self._url("work-items"), wait_until="domcontentloaded")
            page_path = urlparse(page.url).path.rstrip("/")
            if page_path == "/work-items":
                return
            if page_path != "/login":
                raise SystemException(
                    "ACME navigation reached an unsupported authentication page",
                    action="login",
                )

            is_fake = page.locator('[data-testid="username"]').count() > 0
            is_real = page.locator("#email").count() > 0 and page.locator("#password").count() > 0
            if not is_fake and not is_real:
                raise SystemException(
                    "ACME login page does not expose a supported login form",
                    action="login",
                )

            username = self._credential(credentials, "acme_username")
            password = self._credential(credentials, "acme_password")
            if is_fake:
                page.get_by_test_id("username").fill(username)
                page.get_by_test_id("password").fill(password)
                page.get_by_test_id("login").click()
            else:
                page.locator("#email").fill(username)
                page.locator("#password").fill(password)
                page.locator("button[type=submit]").click()

            page.wait_for_load_state("domcontentloaded")
            page_path = urlparse(page.url).path.rstrip("/")
            if page_path == "/login":
                raise SystemException("ACME authentication was rejected", action="login")
            if page_path != "/work-items":
                raise SystemException(
                    "ACME authentication did not reach the work-items page",
                    action="login",
                )
        except SystemException:
            raise
        except Exception as exc:
            raise SystemException("Unable to establish an authenticated ACME session", action="login") from exc

    def discover_open_items(self) -> list[DiscoveredItem]:
        page = self._page_or_raise()
        try:
            page.goto(self._url("work-items"), wait_until="domcontentloaded")
            records: list[DiscoveredItem] = []
            discovered_ids: set[str] = set()
            visited_pages: set[str] = set()

            while True:
                if page.url in visited_pages or len(visited_pages) >= 1000:
                    raise ValueError("work-item pagination loop detected")
                visited_pages.add(page.url)

                is_fake = self._is_fake_page(page)
                if is_fake:
                    for row in page.locator('[data-testid="work-item-row"]').all():
                        work_item_id = validate_work_item_id(row.get_attribute("data-work-item-id") or "")
                        fingerprint = row.get_attribute("data-fingerprint") or ""
                        if not fingerprint:
                            raise ValueError("discovery row has no fingerprint")
                        if work_item_id not in discovered_ids:
                            discovered_ids.add(work_item_id)
                            records.append(DiscoveredItem(work_item_id, fingerprint))
                else:
                    for row in page.locator("table tbody tr").all():
                        cells = row.locator("td").all()
                        if len(cells) < 6:
                            continue
                        status = cells[4].inner_text().strip()
                        if status != "Open":
                            continue
                        wiid = cells[1].inner_text().strip()
                        date = cells[5].inner_text().strip()
                        work_item_id = validate_work_item_id(wiid)
                        if work_item_id not in discovered_ids:
                            discovered_ids.add(work_item_id)
                            records.append(
                                DiscoveredItem(
                                    work_item_id,
                                    self._compute_fingerprint(wiid, status, date),
                                )
                            )

                next_page = self._next_work_items_page(page)
                if not next_page:
                    break
                page.goto(next_page, wait_until="domcontentloaded")

            return records
        except Exception as exc:
            raise SystemException("Unable to discover ACME work items", action="discover") from exc

    def _next_work_items_page(self, page: Page) -> str:
        next_href = ""
        for link in page.locator("nav.woocommerce-pagination a.page-numbers").all():
            if link.inner_text().strip() in {">", "›", "»", "Next"}:
                next_href = link.get_attribute("href") or ""
                break
        if not next_href:
            return ""

        next_url = urljoin(page.url, next_href)
        parsed = urlparse(next_url)
        base = urlparse(self.base_url)
        expected_path = urlparse(self._url("work-items")).path.rstrip("/")
        if (
            parsed.scheme != base.scheme
            or parsed.netloc != base.netloc
            or parsed.username
            or parsed.password
            or parsed.path.rstrip("/") != expected_path
        ):
            raise ValueError("invalid work-item pagination URL")
        return next_url

    def fetch_item(self, work_item_id: str) -> RemoteWorkItem:
        page = self._load_item(work_item_id)
        return self._read_item(page, work_item_id)

    def apply_security_hash(
        self,
        work_item_id: str,
        *,
        expected_hash: str,
        security_hash: str,
    ) -> RemoteWorkItem:
        page = self._load_item(work_item_id)
        current = self._read_item(page, work_item_id)
        is_fake = self._is_fake_page(page)
        if (
            is_fake
            and current.status == "open"
            and current.identity_hash == security_hash
            and current.stored_comment == security_hash
        ):
            return current
        if (
            current.status != "open"
            or current.fingerprint != expected_hash
            or current.identity_hash != security_hash
        ):
            raise RemoteConflictError("work item changed before update")
        try:
            if is_fake:
                page.get_by_test_id("security-hash-input").fill(security_hash)
                page.get_by_test_id("update").click()
                page.wait_for_load_state("domcontentloaded")
                updated = self._read_item(page, work_item_id)
            else:
                updated = self._apply_hash_via_update_form(
                    page,
                    work_item_id,
                    security_hash=security_hash,
                )
        except RemoteConflictError:
            raise
        except Exception as exc:
            raise SystemException("Unable to update ACME work item", action="update_work_item") from exc
        if (
            updated.identity_hash != security_hash
            or updated.stored_comment != security_hash
            or updated.status != "open"
        ):
            raise SystemException("ACME update could not be verified", action="update_work_item")
        return updated

    def close_item(
        self,
        work_item_id: str,
        *,
        expected_hash: str,
        security_hash: str,
    ) -> RemoteWorkItem:
        page = self._load_item(work_item_id)
        current = self._read_item(page, work_item_id)
        if current.identity_hash != security_hash:
            raise RemoteConflictError("work item identity changed before close")
        if current.status == "closed":
            if page.locator('[data-testid="work-item-detail"]').count():
                if current.stored_comment != security_hash:
                    raise RemoteConflictError("closed work item has a different security hash")
            else:
                self._verify_remote_comment(
                    page,
                    work_item_id,
                    security_hash=security_hash,
                    action="close_work_item",
                )
            return replace(
                current,
                stored_comment=security_hash,
                was_already_closed=True,
            )
        if current.status != "open" or current.fingerprint != expected_hash:
            raise RemoteConflictError("work item changed before close")
        try:
            if self._is_fake_page(page):
                page.get_by_test_id("close").click()
                page.wait_for_load_state("domcontentloaded")
                closed = self._read_item(page, work_item_id)
            else:
                closed = self._close_via_update_form(
                    page,
                    work_item_id,
                    security_hash=security_hash,
                )
        except RemoteConflictError:
            raise
        except Exception as exc:
            raise SystemException("Unable to close ACME work item", action="close_work_item") from exc
        if (
            closed.status != "closed"
            or closed.identity_hash != security_hash
            or closed.stored_comment != security_hash
        ):
            raise SystemException("ACME close could not be verified", action="close_work_item")
        return closed

    def _apply_hash_via_update_form(
        self,
        page: Page,
        work_item_id: str,
        *,
        security_hash: str,
    ) -> RemoteWorkItem:
        self._submit_update_form(
            page,
            work_item_id,
            security_hash=security_hash,
            status="Open",
            action="update_work_item",
        )
        page.goto(
            self._url(f"work-items/{quote(work_item_id, safe='')}"),
            wait_until="domcontentloaded",
        )
        return replace(
            self._read_item(page, work_item_id),
            stored_comment=security_hash,
        )

    def _close_via_update_form(
        self,
        page: Page,
        work_item_id: str,
        *,
        security_hash: str,
    ) -> RemoteWorkItem:
        self._submit_update_form(
            page,
            work_item_id,
            security_hash=security_hash,
            status="Completed",
            action="close_work_item",
        )
        page.goto(
            self._url(f"work-items/{quote(work_item_id, safe='')}"),
            wait_until="domcontentloaded",
        )
        return replace(
            self._read_item(page, work_item_id),
            stored_comment=security_hash,
        )

    def _submit_update_form(
        self,
        page: Page,
        work_item_id: str,
        *,
        security_hash: str,
        status: str,
        action: str,
    ) -> None:
        quoted_id = quote(work_item_id, safe="")
        update_url = self._url(f"work-items/update/{quoted_id}")
        page.goto(update_url, wait_until="domcontentloaded")
        page.locator("#newComment").fill(security_hash)
        page.locator("#newStatus").select_option(status)
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda response: "/work-items/edit/" in response.url) as response_info:
            page.locator("#buttonUpdate").click()
        if not response_info.value.ok:
            raise SystemException("ACME update request was rejected", action=action)
        self._verify_remote_comment(
            page,
            work_item_id,
            security_hash=security_hash,
            action=action,
        )

    def _verify_remote_comment(
        self,
        page: Page,
        work_item_id: str,
        *,
        security_hash: str,
        action: str,
    ) -> None:
        page.goto(
            self._url(f"work-items/update/{quote(work_item_id, safe='')}"),
            wait_until="domcontentloaded",
        )
        form_text = page.locator(".panel-body").inner_text()
        stored_comment = self._extract_field(form_text, "Comments")
        if stored_comment != security_hash:
            raise SystemException("Security hash comment was not stored on the remote item", action=action)

    def capture_screenshot(self, work_item_id: str, destination: Path) -> Path:
        validate_work_item_id(work_item_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._page_or_raise().screenshot(path=str(destination), full_page=True)
        except Exception as exc:
            raise SystemException("Unable to capture ACME work-item screenshot", action="screenshot") from exc
        return destination

    def _start(self) -> None:
        if self._page is not None and not self._page.is_closed():
            return
        try:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.action_timeout_ms)
            self._page.set_default_navigation_timeout(self.page_load_timeout_ms)
        except Exception as exc:
            self._close_resources()
            raise SystemException("Unable to launch Chromium", action="browser_start") from exc

    def _healthy_page(self) -> Page:
        try:
            healthy = not (
                self._playwright is None
                or self._browser is None
                or not self._browser.is_connected()
                or self._context is None
                or self._page is None
                or self._page.is_closed()
            )
        except Exception:
            healthy = False
        if not healthy:
            cleanup_error = self._close_resources()
            if cleanup_error is not None:
                raise SystemException(
                    "Browser resources could not be repaired cleanly",
                    action="browser_repair",
                ) from cleanup_error
            self._start()
        return self._page_or_raise()

    @staticmethod
    def _credential(credentials: CredentialProvider, name: str) -> str:
        try:
            return credentials.get(name)
        except CredentialNotFoundError as exc:
            raise SystemException(
                f"Required credential {name!r} is unavailable",
                action="login",
            ) from exc

    @staticmethod
    def _compute_fingerprint(wiid: str, status: str, date: str) -> str:
        # These are the mutable fields exposed on both list and detail views.
        # Client identity is fetched fresh, then guarded by identity_hash before
        # either remote mutation; it is not available during list discovery.
        material = f"{wiid}|{status.lower()}|{date}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _page_or_raise(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise SystemException("Browser page is unavailable", action="browser_session")
        return self._page

    def _load_item(self, work_item_id: str) -> Page:
        work_item_id = validate_work_item_id(work_item_id)
        page = self._page_or_raise()
        try:
            page.goto(self._url(f"work-items/{quote(work_item_id, safe='')}"), wait_until="domcontentloaded")
            if self._is_fake_page(page):
                return page
            if f"/work-items/{quote(work_item_id, safe='')}" in page.url:
                return page
            raise ValueError("work-item detail was not rendered")
        except Exception as exc:
            raise SystemException("Unable to load ACME work item", action="fetch_work_item") from exc

    @staticmethod
    def _is_fake_page(page: Page) -> bool:
        return any(
            page.locator(selector).count() > 0
            for selector in (
                '[data-testid="work-item-row"]',
                '[data-testid="work-item-detail"]',
                '[data-testid="security-hash-input"]',
                '[data-testid="close"]',
            )
        )

    @staticmethod
    def _text(page: Page, test_id: str) -> str:
        return page.get_by_test_id(test_id).inner_text().strip()

    @staticmethod
    def _extract_field(text: str, label: str, *, required: bool = True) -> str:
        match = re.search(rf"{re.escape(label)}:\s*(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        if required:
            raise ValueError(f"Field {label!r} not found in detail page")
        return ""

    @staticmethod
    def _type_code(description: str) -> str:
        code = _TYPE_DESCRIPTION_TO_CODE.get(description.lower())
        if code:
            return code
        raise ValueError(f"Unknown work item type: {description!r}")

    def _read_item(self, page: Page, work_item_id: str) -> RemoteWorkItem:
        try:
            if page.locator('[data-testid="work-item-detail"]').count():
                client_id = self._text(page, "client-id")
                wiid = self._text(page, "wiid")
                return RemoteWorkItem(
                    work_item_id=work_item_id,
                    client_id=client_id,
                    wiid=wiid,
                    item_type=self._text(page, "item-type"),
                    status=self._text(page, "status").lower(),
                    identity_hash=compute_identity_hash(client_id, wiid),
                    fingerprint=self._text(page, "fingerprint"),
                    stored_comment=self._text(page, "security-hash"),
                )

            text = page.locator(".panel-body").inner_text()
            return self._parse_real_item_text(text, work_item_id)
        except Exception as exc:
            raise SystemException("Unable to parse ACME work item", action="fetch_work_item") from exc

    @classmethod
    def _parse_real_item_text(cls, text: str, work_item_id: str) -> RemoteWorkItem:
        client_id = cls._extract_field(text, "Client ID", required=False)
        wiid = cls._extract_field(text, "WIID")
        item_type_full = cls._extract_field(text, "Type")
        status_raw = cls._extract_field(text, "Status")
        status = "closed" if status_raw.lower() == "completed" else status_raw.lower()
        date = cls._extract_field(text, "Date")
        return RemoteWorkItem(
            work_item_id=work_item_id,
            client_id=client_id,
            wiid=wiid,
            item_type=cls._type_code(item_type_full),
            status=status,
            identity_hash=compute_identity_hash(client_id, wiid),
            fingerprint=cls._compute_fingerprint(wiid, status, date),
        )

    def _url(self, relative: str) -> str:
        return urljoin(self.base_url, relative)

    def _close_resources(self) -> Exception | None:
        first_error: Exception | None = None
        for resource, method in (
            (self._page, "close"),
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    first_error = first_error or exc
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        return first_error


def require_authenticated_session(ctx: ProcessContext) -> BrowserSession:
    session = ctx.resources.get("browser_session")
    if not isinstance(session, BrowserSession):
        raise SystemException(
            "Process resource 'browser_session' is missing or invalid",
            action="browser_session",
        )
    session.ensure_authenticated(ctx.credentials)
    return session
