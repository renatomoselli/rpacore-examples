from __future__ import annotations

import hashlib
import html
import threading
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class FakeWorkItem:
    work_item_id: str
    client_id: str
    wiid: str
    item_type: str = "WI5"
    status: str = "open"
    security_hash: str = ""
    version: int = 1

    @property
    def fingerprint(self) -> str:
        material = (
            f"{self.work_item_id}|{self.client_id}|{self.wiid}|{self.item_type}|"
            f"{self.status}|{self.security_hash}|{self.version}"
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class FakeAcmeState:
    username: str = "robot@example.test"
    password: str = "correct-horse"
    items: dict[str, FakeWorkItem] = field(default_factory=dict)
    sessions: set[str] = field(default_factory=set)
    update_counts: dict[str, int] = field(default_factory=dict)
    close_counts: dict[str, int] = field(default_factory=dict)
    discovery_page_size: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    def add_item(
        self,
        work_item_id: str,
        *,
        client_id: str,
        wiid: str,
        item_type: str = "WI5",
        status: str = "open",
        security_hash: str = "",
    ) -> FakeWorkItem:
        with self.lock:
            item = FakeWorkItem(
                work_item_id,
                client_id,
                wiid,
                item_type=item_type,
                status=status,
                security_hash=security_hash,
            )
            self.items[work_item_id] = item
            return item

    def mutate(self, work_item_id: str, *, client_id: str | None = None) -> None:
        with self.lock:
            item = self.items[work_item_id]
            if client_id is not None:
                item.client_id = client_id
            item.version += 1

    def expire_sessions(self) -> None:
        with self.lock:
            self.sessions.clear()


class _FakeAcmeHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: FakeAcmeState) -> None:
        super().__init__(address, _FakeAcmeHandler)
        self.state = state


class _FakeAcmeHandler(BaseHTTPRequestHandler):
    server: _FakeAcmeHttpServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/login"}:
            self._login_page()
            return
        if not self._authenticated():
            self._redirect("/login")
            return
        if path == "/work-items":
            self._discovery_page(parse_qs(parsed.query))
            return
        if path.startswith("/work-items/"):
            self._item_page(unquote(path.removeprefix("/work-items/")))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        form = self._read_form()
        if path == "/login":
            self._login(form)
            return
        if not self._authenticated():
            self._redirect("/login")
            return
        if path.startswith("/work-items/") and path.endswith("/update"):
            work_item_id = unquote(path[len("/work-items/") : -len("/update")])
            self._update(work_item_id, form)
            return
        if path.startswith("/work-items/") and path.endswith("/close"):
            work_item_id = unquote(path[len("/work-items/") : -len("/close")])
            self._close(work_item_id, form)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _authenticated(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session = cookie.get("session")
        if session is None:
            return False
        with self.server.state.lock:
            return session.value in self.server.state.sessions

    def _login(self, form: dict[str, str]) -> None:
        state = self.server.state
        if form.get("username") != state.username or form.get("password") != state.password:
            self._login_page(error="Invalid username or password")
            return
        token = uuid.uuid4().hex
        with state.lock:
            state.sessions.add(token)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Set-Cookie", f"session={token}; HttpOnly; SameSite=Lax; Path=/")
        self.send_header("Location", "/work-items")
        self.end_headers()

    def _login_page(self, error: str = "") -> None:
        error_html = f'<p data-testid="login-error">{html.escape(error)}</p>' if error else ""
        self._html(
            f"""<!doctype html><html><body>
            <h1>ACME Login</h1>{error_html}
            <form method="post" action="/login">
              <input data-testid="username" name="username">
              <input data-testid="password" name="password" type="password">
              <button data-testid="login" type="submit">Login</button>
            </form></body></html>"""
        )

    def _discovery_page(self, query: dict[str, list[str]]) -> None:
        with self.server.state.lock:
            items = [item for item in self.server.state.items.values() if item.status == "open"]
            items = sorted(items, key=lambda value: value.work_item_id)
            page_size = self.server.state.discovery_page_size
            page_number = max(1, int(query.get("page", ["1"])[-1]))
            total_pages = 1
            if page_size > 0:
                total_pages = max(1, (len(items) + page_size - 1) // page_size)
                start = (page_number - 1) * page_size
                items = items[start : start + page_size]
            rows = "".join(
                f'<tr data-testid="work-item-row" data-work-item-id="{html.escape(item.work_item_id)}" '
                f'data-fingerprint="{item.fingerprint}"><td><a href="/work-items/{html.escape(item.work_item_id)}">'
                f'{html.escape(item.work_item_id)}</a></td></tr>'
                for item in items
            )
            pagination = ""
            if page_number < total_pages:
                pagination = (
                    '<nav class="woocommerce-pagination navigation">'
                    f'<a class="page-numbers" href="/work-items?page={page_number + 1}">&gt;</a>'
                    "</nav>"
                )
        self._html(
            f"""<!doctype html><html><body>
            <div data-testid="authenticated-user">robot</div>
            <table><tbody>{rows}</tbody></table>{pagination}</body></html>"""
        )

    def _item_page(self, work_item_id: str) -> None:
        with self.server.state.lock:
            item = self.server.state.items.get(work_item_id)
            if item is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            escaped_id = html.escape(item.work_item_id)
            controls = ""
            if item.status == "open":
                controls = f"""
                <form method="post" action="/work-items/{escaped_id}/update">
                  <input type="hidden" name="expected_hash" value="{item.fingerprint}">
                  <input data-testid="security-hash-input" name="security_hash" value="{html.escape(item.security_hash)}">
                  <button data-testid="update" type="submit">Update</button>
                </form>
                <form method="post" action="/work-items/{escaped_id}/close">
                  <input type="hidden" name="expected_hash" value="{item.fingerprint}">
                  <button data-testid="close" type="submit">Close</button>
                </form>"""
            body = f"""<!doctype html><html><body>
            <div data-testid="authenticated-user">robot</div>
            <main data-testid="work-item-detail">
              <span data-testid="client-id">{html.escape(item.client_id)}</span>
              <span data-testid="wiid">{html.escape(item.wiid)}</span>
              <span data-testid="item-type">{html.escape(item.item_type)}</span>
              <span data-testid="status">{html.escape(item.status)}</span>
              <span data-testid="security-hash">{html.escape(item.security_hash)}</span>
              <span data-testid="fingerprint">{item.fingerprint}</span>
              {controls}
            </main></body></html>"""
        self._html(body)

    def _update(self, work_item_id: str, form: dict[str, str]) -> None:
        with self.server.state.lock:
            item = self.server.state.items.get(work_item_id)
            if item is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            desired = form.get("security_hash", "")
            if item.security_hash != desired:
                if item.status != "open" or form.get("expected_hash") != item.fingerprint:
                    self.send_error(HTTPStatus.CONFLICT)
                    return
                item.security_hash = desired
                item.version += 1
                self.server.state.update_counts[work_item_id] = self.server.state.update_counts.get(work_item_id, 0) + 1
        self._redirect(f"/work-items/{work_item_id}")

    def _close(self, work_item_id: str, form: dict[str, str]) -> None:
        with self.server.state.lock:
            item = self.server.state.items.get(work_item_id)
            if item is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if item.status != "closed":
                if form.get("expected_hash") != item.fingerprint:
                    self.send_error(HTTPStatus.CONFLICT)
                    return
                item.status = "closed"
                item.version += 1
                self.server.state.close_counts[work_item_id] = self.server.state.close_counts.get(work_item_id, 0) + 1
        self._redirect(f"/work-items/{work_item_id}")

    def _read_form(self) -> dict[str, str]:
        size = int(self.headers.get("Content-Length", "0"))
        parsed = parse_qs(self.rfile.read(size).decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items()}

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class FakeAcmeServer:
    def __init__(self) -> None:
        self.state = FakeAcmeState()
        self._server = _FakeAcmeHttpServer(("127.0.0.1", 0), self.state)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> FakeAcmeServer:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False

    def items(self) -> Iterator[FakeWorkItem]:
        with self.state.lock:
            yield from list(self.state.items.values())
