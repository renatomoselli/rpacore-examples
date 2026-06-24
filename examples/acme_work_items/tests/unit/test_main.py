from __future__ import annotations

import pytest
import sqlite3
from rpacore import (
    BusinessException,
    Engine,
    QueueItem,
    QueueRunSummary,
    Skill,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    list_transactions,
)

from main import _project_outcome, _run_summary_transaction, _validate_config, build_transaction, scan_inbox
from skills._session import DiscoveredItem
from tests.conftest import FakeCredentials


def test_build_transaction_has_explicit_five_skill_order() -> None:
    transaction = build_transaction(
        QueueItem(reference="acme-1001", payload={"work_item_id": "1001", "discovered_hash": "v1"}),
        run_id="run",
    )
    assert [skill.name for skill in transaction.ordered_skills()] == [
        "fetch_work_item",
        "validate_work_item",
        "compute_security_hash",
        "update_work_item",
        "close_work_item",
    ]


def test_build_transaction_rejects_payload_url() -> None:
    forbidden_key = "work_item_" + "url"
    with pytest.raises(SystemException, match="exactly"):
        build_transaction(
            QueueItem(
                reference="bad",
                payload={"work_item_id": "1", "discovered_hash": "v1", forbidden_key: "https://evil.test"},
            )
        )


def test_validate_config_rejects_bool_integer(example_config) -> None:
    example_config["report_max_records"] = True
    with pytest.raises(SystemException, match="invalid type|must be int"):
        _validate_config(example_config)


def test_validate_config_rejects_embedded_base_url_credentials(example_config) -> None:
    example_config["base_url"] = "https://user:secret@example.test"
    with pytest.raises(SystemException, match="embedded"):
        _validate_config(example_config)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("max_retries",), -1),
        (("retry_delay",), -0.1),
        (("retry_delay",), float("inf")),
        (("retry_backoff",), 0.5),
        (("retry_backoff",), float("nan")),
        (("report_max_records",), 0),
        (("page_load_timeout_ms",), 0),
        (("action_timeout_ms",), 0),
        (("log_level",), "VERBOSE"),
        (("log_format",), "yaml"),
        (("credential_provider",), "file"),
        (("transaction_db_path",), " "),
        (("screenshot_dir",), " "),
        (("report_dir",), " "),
        (("base_url",), "relative/path"),
        (("queue", "db_path"), ""),
        (("queue", "lease_timeout"), 0),
        (("queue", "max_retries"), -1),
    ],
)
def test_validate_config_rejects_invalid_ranges_and_enums(example_config, path, value) -> None:
    target = example_config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(SystemException):
        _validate_config(example_config)


def test_malformed_discovery_record_is_not_queued(example_config) -> None:
    class InvalidDiscoverySession:
        def __enter__(self):
            return {"browser_session": self}

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ensure_authenticated(self, credentials):
            return None

        def discover_open_items(self):
            return [DiscoveredItem("../escape", "fingerprint")]

    queue = SqliteQueue(example_config["queue"])
    with pytest.raises(SystemException, match="invalid identifier"):
        scan_inbox(
            example_config,
            queue,
            FakeCredentials(),
            session_factory=lambda config: InvalidDiscoverySession(),
        )
    assert queue.next_item("unit") is None


def test_project_outcome_classifies_business_failure_without_full_state() -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    failed = SkillFailure(name="validate", execution_order=1)
    failed.status = Status.FAILED
    failed.exceptions.append(BusinessException("bad data", action="validate", stop=True))
    transaction = Transaction(reference="acme-1", state={"secret": "must-not-copy"}, skills=[failed])
    transaction.status = Status.FAILED
    record = _project_outcome(item, transaction, None)
    assert record["classification"] == "business"
    assert record["failed_skill"] == "validate"
    assert "secret" not in record


def test_project_outcome_covers_transaction_build_failure() -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    record = _project_outcome(item, None, SystemException("build failed", action="build"))
    assert record["classification"] == "system"
    assert record["transaction_id"] == ""


def test_project_outcome_sanitizes_persistence_error() -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    record = _project_outcome(item, None, sqlite3.OperationalError("database path details"))
    assert record["classification"] == "unexpected"
    assert record["message"] == "Unexpected item-processing error"


def test_failed_summary_transaction_is_persisted(monkeypatch, example_config) -> None:
    def fail(self, ctx):
        raise SystemException("summary failed", action=self.name)

    monkeypatch.setattr("main.WriteSummary.execute", fail)
    with pytest.raises(SystemException, match="summary transaction failed"):
        _run_summary_transaction(
            example_config,
            Engine(max_retries=0),
            run_id="failed-summary",
            records=[],
            omitted_record_count=0,
            queue_summary=QueueRunSummary(),
            credentials=FakeCredentials(),
        )
    persisted = list_transactions(str(example_config["transaction_db_path"]), limit=10)
    assert persisted[0].reference == "acme-summary-failed-summary"
    assert persisted[0].status is Status.FAILED


class SkillFailure(Skill):
    def execute(self, ctx) -> None:
        return
