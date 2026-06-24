from __future__ import annotations

from rpacore import BusinessException, Status, SystemException

from skills._session import RemoteConflictError, RemoteWorkItem
from skills.update_work_item import UpdateWorkItem
from tests.conftest import run_skill


class UpdateSession:
    def __init__(self, *, conflict: bool = False, status: str = "open") -> None:
        self.conflict = conflict
        self.status = status

    def apply_security_hash(self, work_item_id: str, *, expected_hash: str, security_hash: str) -> RemoteWorkItem:
        if self.conflict:
            raise RemoteConflictError("changed")
        return RemoteWorkItem(
            work_item_id,
            "C",
            "WI",
            "WI5",
            self.status,
            security_hash,
            "updated",
            stored_comment=security_hash,
        )


def _state() -> dict[str, object]:
    return {
        "work_item_id": "1001",
        "fetched_hash": "original",
        "security_hash": "desired",
        "update_intent_id": "intent",
    }


def test_update_persists_close_intent(monkeypatch, example_config) -> None:
    monkeypatch.setattr("skills.update_work_item.require_authenticated_session", lambda ctx: UpdateSession())
    transaction = run_skill(
        UpdateWorkItem(name="update", execution_order=1),
        state=_state(),
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state["close_intent"] == {
        "work_item_id": "1001",
        "expected_hash": "updated",
        "security_hash": "desired",
    }


def test_update_classifies_concurrency_as_business(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "skills.update_work_item.require_authenticated_session",
        lambda ctx: UpdateSession(conflict=True),
    )
    transaction = run_skill(
        UpdateWorkItem(name="update", execution_order=1),
        state=_state(),
        config=example_config,
    )
    exception = transaction.failed_skills()[0].exceptions[-1]
    assert isinstance(exception, BusinessException)
    assert exception.stop is True


def test_update_rejects_already_closed_without_close_intent(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "skills.update_work_item.require_authenticated_session",
        lambda ctx: UpdateSession(status="closed"),
    )
    transaction = run_skill(
        UpdateWorkItem(name="update", execution_order=1),
        state=_state(),
        config=example_config,
    )
    exception = transaction.failed_skills()[0].exceptions[-1]
    assert isinstance(exception, BusinessException)
    assert exception.stop is True


def test_update_rejects_unexpected_remote_status(monkeypatch, example_config) -> None:
    monkeypatch.setattr(
        "skills.update_work_item.require_authenticated_session",
        lambda ctx: UpdateSession(status="pending"),
    )
    transaction = run_skill(
        UpdateWorkItem(name="update", execution_order=1),
        state=_state(),
        config=example_config,
    )
    exception = transaction.failed_skills()[0].exceptions[-1]
    assert isinstance(exception, SystemException)
    assert "could not be verified" in str(exception)
