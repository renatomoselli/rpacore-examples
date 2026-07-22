from __future__ import annotations

import json
from pathlib import Path

import pytest
from rpacore import Status, list_transactions

from main import run_example
from tests.conftest import browser_session


pytestmark = pytest.mark.integration


def test_full_queue_workflow_persists_state_and_real_artifacts(
    example_config,
    acme_server,
    credentials,
) -> None:
    item = acme_server.state.add_item("1001", client_id="C123", wiid="WI456")

    result = run_example(
        example_config,
        credentials=credentials,
        session_factory=browser_session,
    )

    assert result.enqueued == 1
    assert result.queue_summary.processed == 1
    assert result.queue_summary.completed == 1
    assert result.queue_summary.failed == 0
    assert item.status == "closed"
    assert acme_server.state.update_counts == {"1001": 1}
    assert acme_server.state.close_counts == {"1001": 1}

    transactions = list_transactions(str(example_config["transaction_db_path"]), limit=20)
    item_transaction = next(tx for tx in transactions if tx.reference == "acme-1001")
    assert item_transaction.status is Status.SUCCESSFUL
    assert item_transaction.state["closed"] is True
    assert item_transaction.state["idempotency_outcome"] == "closed"
    assert Path(item_transaction.artifacts[0].path).is_file()
    assert result.summary_transaction.status is Status.SUCCESSFUL
    summary_path = Path(result.summary_transaction.state["summary_path"])
    assert summary_path.is_file()
    assert json.loads(summary_path.read_text(encoding="utf-8"))["records"][0]["transaction_status"] == "successful"

    persisted_text = json.dumps(
        [
            {"state": tx.state, "metadata": tx.metadata, "artifacts": [a.metadata for a in tx.artifacts]}
            for tx in transactions
        ]
    )
    assert credentials.values["acme_username"] not in persisted_text
    assert credentials.values["acme_password"] not in persisted_text


def test_concurrent_change_is_terminal_business_failure(
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="original", wiid="WI-1")
    example_config["queue"]["max_retries"] = 2
    calls = 0

    def factory(config):
        nonlocal calls
        calls += 1
        if calls == 2:
            acme_server.state.mutate("1001", client_id="changed")
        return browser_session(config)

    result = run_example(example_config, credentials=credentials, session_factory=factory)
    assert result.queue_summary.processed == 1
    assert result.queue_summary.failed == 1
    assert acme_server.state.update_counts == {}
    assert acme_server.state.close_counts == {}
    report = json.loads(Path(result.summary_transaction.state["summary_path"]).read_text(encoding="utf-8"))
    assert report["records"][0]["outcome"]["category"] == "business_failed"
    assert report["records"][0]["diagnostics"]["error_type"] == "business_exception"


def test_item_closed_after_discovery_is_terminal_without_retry(
    example_config,
    acme_server,
    credentials,
) -> None:
    item = acme_server.state.add_item("1001", client_id="original", wiid="WI-1")
    example_config["queue"]["max_retries"] = 2
    calls = 0

    def factory(config):
        nonlocal calls
        calls += 1
        if calls == 2:
            item.status = "closed"
            item.version += 1
        return browser_session(config)

    result = run_example(example_config, credentials=credentials, session_factory=factory)
    assert result.queue_summary.processed == 1
    assert result.queue_summary.failed == 1
    assert acme_server.state.update_counts == {}
    assert acme_server.state.close_counts == {}
