from __future__ import annotations

import hashlib

import pytest
from rpacore import SystemException, list_transactions

from main import run_example
from steps._session import BrowserSession, RemoteConflictError
from tests.conftest import browser_session


pytestmark = pytest.mark.integration


class FaultAfterSideEffectSession(BrowserSession):
    def __init__(self, config, tracker: dict[str, bool], fail_at: str) -> None:
        super().__init__(
            str(config["base_url"]),
            headless=True,
            page_load_timeout_ms=int(config["page_load_timeout_ms"]),
            action_timeout_ms=int(config["action_timeout_ms"]),
        )
        self.tracker = tracker
        self.fail_at = fail_at

    def apply_security_hash(self, work_item_id: str, *, expected_hash: str, security_hash: str):
        result = super().apply_security_hash(
            work_item_id,
            expected_hash=expected_hash,
            security_hash=security_hash,
        )
        if self.fail_at == "update" and not self.tracker.get("update"):
            self.tracker["update"] = True
            raise SystemException("simulated interruption after update", action="test")
        return result

    def close_item(self, work_item_id: str, *, expected_hash: str, security_hash: str):
        result = super().close_item(
            work_item_id,
            expected_hash=expected_hash,
            security_hash=security_hash,
        )
        if self.fail_at == "close" and not self.tracker.get("close"):
            self.tracker["close"] = True
            raise SystemException("simulated interruption after close", action="test")
        return result


@pytest.mark.parametrize("fail_at", ["update", "close"])
def test_queue_resume_does_not_duplicate_remote_side_effect(
    fail_at,
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    example_config["queue"]["max_retries"] = 1
    tracker: dict[str, bool] = {}

    def factory(config):
        return FaultAfterSideEffectSession(config, tracker, fail_at)

    result = run_example(example_config, credentials=credentials, session_factory=factory)

    assert tracker[fail_at] is True
    assert result.queue_summary.processed == 2
    assert result.queue_summary.completed == 1
    assert result.queue_summary.failed == 1
    assert acme_server.state.update_counts["1001"] == 1
    assert acme_server.state.close_counts["1001"] == 1
    item_transactions = [
        transaction
        for transaction in list_transactions(str(example_config["transaction_db_path"]), limit=20)
        if transaction.reference == "acme-1001"
    ]
    assert len(item_transactions) == 1
    assert all(step.status == "successful" for step in item_transactions[0].steps)


def test_applied_hash_fast_path_rejects_changed_identity(
    example_config,
    acme_server,
    credentials,
) -> None:
    item = acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    expected_hash = item.fingerprint
    security_hash = hashlib.sha1(b"C-1WI-1").hexdigest()

    with browser_session(example_config) as resources:
        session = resources["browser_session"]
        session.ensure_authenticated(credentials)
        session.apply_security_hash(
            "1001",
            expected_hash=expected_hash,
            security_hash=security_hash,
        )
        acme_server.state.mutate("1001", client_id="C-2")

        with pytest.raises(RemoteConflictError, match="changed before update"):
            session.apply_security_hash(
                "1001",
                expected_hash=expected_hash,
                security_hash=security_hash,
            )


def test_close_rejects_changed_identity_before_remote_mutation(
    example_config,
    acme_server,
    credentials,
) -> None:
    item = acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    security_hash = hashlib.sha1(b"C-1WI-1").hexdigest()

    with browser_session(example_config) as resources:
        session = resources["browser_session"]
        session.ensure_authenticated(credentials)
        updated = session.apply_security_hash(
            "1001",
            expected_hash=item.fingerprint,
            security_hash=security_hash,
        )
        acme_server.state.mutate("1001", client_id="C-2")

        with pytest.raises(RemoteConflictError, match="identity changed before close"):
            session.close_item(
                "1001",
                expected_hash=updated.fingerprint,
                security_hash=security_hash,
            )

    assert acme_server.state.items["1001"].status == "open"
    assert acme_server.state.close_counts.get("1001", 0) == 0
