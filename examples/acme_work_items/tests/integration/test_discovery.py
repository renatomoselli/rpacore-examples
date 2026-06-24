from __future__ import annotations

import sqlite3

import pytest
from rpacore import SqliteQueue

from main import scan_inbox
from tests.conftest import browser_session


pytestmark = pytest.mark.integration


def _queue_count(path: str) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM queue_items").fetchone()[0])


def test_discovery_uses_real_browser_and_add_once(example_config, acme_server, credentials) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    acme_server.state.add_item("1002", client_id="C-2", wiid="WI-2")
    acme_server.state.add_item("1003", client_id="C-3", wiid="WI-3", status="closed")
    queue = SqliteQueue(example_config["queue"])

    assert scan_inbox(example_config, queue, credentials, session_factory=browser_session) == 2
    assert scan_inbox(example_config, queue, credentials, session_factory=browser_session) == 0
    assert _queue_count(str(example_config["queue"]["db_path"])) == 2

    claimed = queue.next_item("assert-payload")
    assert claimed is not None
    assert set(claimed.payload) == {"work_item_id", "discovered_hash"}
    assert "work_item_" + "url" not in claimed.payload


def test_discovery_session_is_closed_before_return(example_config, acme_server, credentials) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    sessions = []

    def factory(config):
        session = browser_session(config)
        sessions.append(session)
        return session

    scan_inbox(example_config, SqliteQueue(example_config["queue"]), credentials, session_factory=factory)
    assert sessions[0]._page is None
    assert sessions[0]._browser is None


def test_discovery_traverses_all_pages(example_config, acme_server, credentials) -> None:
    acme_server.state.discovery_page_size = 2
    for number in range(1, 6):
        acme_server.state.add_item(
            f"10{number}",
            client_id=f"C-{number}",
            wiid=f"WI-{number}",
        )
    acme_server.state.add_item("999", client_id="closed", wiid="WI-X", status="closed")
    queue = SqliteQueue(example_config["queue"])

    assert scan_inbox(example_config, queue, credentials, session_factory=browser_session) == 5
    assert _queue_count(str(example_config["queue"]["db_path"])) == 5
