from __future__ import annotations

from rpacore import Status, SystemException

from steps._session import RemoteWorkItem
from steps.fetch_work_item import FetchWorkItem
from tests.conftest import run_step


class FetchSession:
    def fetch_item(self, work_item_id: str) -> RemoteWorkItem:
        assert work_item_id == "1001"
        return RemoteWorkItem("1001", "C-42", "WI-9", "WI5", "open", "", "v1")


def test_fetch_records_json_safe_remote_snapshot(monkeypatch, example_config) -> None:
    monkeypatch.setattr("steps.fetch_work_item.require_authenticated_session", lambda ctx: FetchSession())
    transaction = run_step(
        FetchWorkItem(name="fetch", execution_order=1),
        state={"work_item_id": "1001"},
        config=example_config,
    )

    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state == {
        "work_item_id": "1001",
        "client_id": "C-42",
        "wiid": "WI-9",
        "fetched_type": "WI5",
        "fetched_status": "open",
        "fetched_hash": "v1",
    }


def test_fetch_sanitizes_unexpected_failures(monkeypatch, example_config) -> None:
    def fail(ctx):
        raise RuntimeError("raw browser detail")

    monkeypatch.setattr("steps.fetch_work_item.require_authenticated_session", fail)
    transaction = run_step(
        FetchWorkItem(name="fetch", execution_order=1),
        state={"work_item_id": "1001"},
        config=example_config,
    )
    assert transaction.status is Status.FAILED
    exception = transaction.failed_steps()[0].exceptions[-1]
    assert isinstance(exception, SystemException)
    assert "raw browser detail" not in str(exception)
