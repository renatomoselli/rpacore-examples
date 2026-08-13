from __future__ import annotations

from pathlib import Path

import pytest
from rpacore import BusinessException, Status, SystemException

from steps._session import RemoteConflictError, RemoteWorkItem
from steps.close_work_item import CloseWorkItem
from tests.conftest import run_step


class CloseSession:
    def __init__(
        self,
        *,
        replay: bool = False,
        conflict: bool = False,
        screenshot_failure: bool = False,
    ) -> None:
        self.replay = replay
        self.conflict = conflict
        self.screenshot_failure = screenshot_failure

    def close_item(
        self,
        work_item_id: str,
        *,
        expected_hash: str,
        security_hash: str,
    ) -> RemoteWorkItem:
        if self.conflict:
            raise RemoteConflictError("changed")
        return RemoteWorkItem(
            work_item_id,
            "C",
            "WI",
            "WI5",
            "closed",
            "desired",
            "closed-fingerprint",
            stored_comment="desired",
            was_already_closed=self.replay,
        )

    def capture_screenshot(self, work_item_id: str, destination: Path) -> Path:
        if self.screenshot_failure:
            raise SystemException("screenshot failed", action="screenshot")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"png")
        return destination


def _state() -> dict[str, object]:
    return {
        "work_item_id": "1001",
        "security_hash": "desired",
        "close_intent": {
            "work_item_id": "1001",
            "expected_hash": "updated",
            "security_hash": "desired",
        },
    }


def test_close_registers_real_screenshot_artifact(monkeypatch, example_config) -> None:
    monkeypatch.setattr("steps.close_work_item.require_authenticated_session", lambda ctx: CloseSession())
    transaction = run_step(
        CloseWorkItem(name="close", execution_order=1),
        state=_state(),
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state["idempotency_outcome"] == "closed"
    assert Path(transaction.artifacts[0].path).is_file()


def test_close_recognizes_authorized_replay(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "steps.close_work_item.require_authenticated_session",
        lambda ctx: CloseSession(replay=True),
    )
    transaction = run_step(
        CloseWorkItem(name="close", execution_order=1),
        state=_state(),
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state["idempotency_outcome"] == "already_closed"


def test_close_conflict_is_terminal_business_failure(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "steps.close_work_item.require_authenticated_session",
        lambda ctx: CloseSession(conflict=True),
    )
    transaction = run_step(
        CloseWorkItem(name="close", execution_order=1),
        state=_state(),
        config=example_config,
    )
    assert isinstance(transaction.failed_steps()[0].exceptions[-1], BusinessException)


@pytest.mark.parametrize(
    "close_intent",
    [
        {"work_item_id": "other", "expected_hash": "updated", "security_hash": "desired"},
        {"work_item_id": "1001", "expected_hash": "updated", "security_hash": "other"},
        {"work_item_id": "1001", "expected_hash": 123, "security_hash": "desired"},
    ],
)
def test_close_rejects_mismatched_durable_intent(close_intent, example_config) -> None:
    state = _state()
    state["close_intent"] = close_intent

    transaction = run_step(
        CloseWorkItem(name="close", execution_order=1),
        state=state,
        config=example_config,
    )

    exception = transaction.failed_steps()[0].exceptions[-1]
    assert isinstance(exception, BusinessException)
    assert exception.halts_remaining_steps is True
    assert "does not authorize" in str(exception)


def test_screenshot_failure_preserves_verified_remote_close_outcome(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "steps.close_work_item.require_authenticated_session",
        lambda ctx: CloseSession(screenshot_failure=True),
    )
    transaction = run_step(
        CloseWorkItem(name="close", execution_order=1),
        state=_state(),
        config=example_config,
    )

    assert transaction.status is Status.FAILED
    assert transaction.state["closed"] is True
    assert transaction.state["idempotency_outcome"] == "closed"
    assert transaction.artifacts == []
