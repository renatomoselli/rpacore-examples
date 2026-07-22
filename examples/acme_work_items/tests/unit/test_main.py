from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
import sqlite3
from rpacore import (
    BusinessException,
    Engine,
    OutcomeCategory,
    QueueItem,
    QueueRunSummary,
    RetryDisposition,
    Skill,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    list_transactions,
)

import main as acme_main
from main import _load_example_config, _project_outcome, _run_summary_transaction, _validate_config, build_transaction, scan_inbox
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
    with pytest.raises(SystemException, match="work_item_url"):
        build_transaction(
            QueueItem(
                reference="bad",
                payload={"work_item_id": "1", "discovered_hash": "v1", forbidden_key: "https://evil.test"},
            )
        )


def test_build_transaction_rejects_non_object_payload() -> None:
    item = QueueItem(reference="bad", payload=None)  # type: ignore[arg-type]

    with pytest.raises(SystemException, match="payload must be an object"):
        build_transaction(item)


def test_build_transaction_accepts_framework_metadata() -> None:
    transaction = build_transaction(
        QueueItem(
            reference="acme-1001",
            payload={
                "work_item_id": "1001",
                "discovered_hash": "v1",
                "_queue_claimed_at": "2026-06-25T00:00:00Z",
            },
        ),
        run_id="run",
    )

    assert transaction.metadata["work_item_id"] == "1001"
    assert transaction.metadata["run_id"] == "run"


def test_validate_config_rejects_bool_integer(example_config) -> None:
    example_config["report_max_records"] = True
    with pytest.raises(SystemException, match="expected int"):
        _validate_config(example_config)


def test_validate_config_rejects_embedded_base_url_credentials(example_config) -> None:
    example_config["base_url"] = "https://user:secret@example.test"
    with pytest.raises(SystemException, match="embedded"):
        _validate_config(example_config)


def test_validate_config_rejects_non_mapping_queue(example_config) -> None:
    example_config["queue"] = "not-a-table"

    with pytest.raises(SystemException, match="queue"):
        _validate_config(example_config)


@pytest.mark.parametrize(
    ("log_format", "expected_options"),
    [
        ("json", {"fmt": "json", "json_version": 2}),
        ("text", {"fmt": "text"}),
    ],
)
def test_main_selects_json_schema_only_for_json_output(
    monkeypatch,
    example_config,
    log_format,
    expected_options,
) -> None:
    options: dict[str, object] = {}
    example_config["log_format"] = log_format
    monkeypatch.setattr(acme_main, "_load_example_config", lambda: example_config)
    monkeypatch.setattr(acme_main, "configure_logger", lambda **kwargs: options.update(kwargs))
    monkeypatch.setattr(acme_main, "run_example", lambda config: object())
    monkeypatch.setattr(acme_main, "_log_run_summary", lambda result: None)

    acme_main.main()

    assert options == {"level": str(example_config["log_level"]), **expected_options}


def test_load_example_config_resolves_paths_without_mutating_input(tmp_path, monkeypatch, example_config) -> None:
    config = deepcopy(example_config)
    config.update(
        {
            "transaction_db_path": "state/transactions.db",
            "screenshot_dir": "screenshots",
            "report_dir": "reports",
        }
    )
    config["queue"] = {
        "db_path": "state/queue.db",
        "lease_timeout": 30,
        "max_retries": 0,
    }
    original = deepcopy(config)
    monkeypatch.setattr(acme_main, "PROJECT_ROOT", tmp_path)

    def fake_load_config(path, *, require_file):
        assert path == tmp_path / "config.toml"
        assert require_file is True
        return config

    monkeypatch.setattr(acme_main, "load_config", fake_load_config)

    validated = _load_example_config()

    assert config == original
    assert validated["transaction_db_path"] == str(tmp_path / "state" / "transactions.db")
    assert validated["screenshot_dir"] == str(tmp_path / "screenshots")
    assert validated["report_dir"] == str(tmp_path / "reports")
    assert validated["queue"] == {
        "db_path": str(tmp_path / "state" / "queue.db"),
        "lease_timeout": 30,
        "max_retries": 0,
    }
    assert "queue.db_path" not in validated


@pytest.mark.parametrize(
    "path_key",
    ("transaction_db_path", "screenshot_dir", "report_dir", "queue.db_path"),
)
def test_load_example_config_rejects_each_path_escape(tmp_path, monkeypatch, example_config, path_key) -> None:
    config = deepcopy(example_config)
    config.update(
        {
            "transaction_db_path": "state/transactions.db",
            "screenshot_dir": "screenshots",
            "report_dir": "reports",
        }
    )
    config["queue"] = {
        "db_path": "state/queue.db",
        "lease_timeout": 30,
        "max_retries": 0,
    }
    if path_key == "queue.db_path":
        config["queue"]["db_path"] = "../outside.db"
    else:
        config[path_key] = "../outside"
    monkeypatch.setattr(acme_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(acme_main, "load_config", lambda _path, *, require_file: config)

    with pytest.raises(SystemException, match="resolves outside root"):
        _load_example_config()


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
    transaction.outcome_category = OutcomeCategory.BUSINESS_FAILED
    transaction.retry_disposition = RetryDisposition.NOT_REQUESTED
    record = _project_outcome(item, transaction, None)
    assert record["outcome"] == {
        "category": "business_failed",
        "retry_disposition": "not_requested",
        "failure_code": "",
    }
    assert record["diagnostics"]["failed_skill"] == "validate"
    assert record["diagnostics"]["error_type"] == "business_exception"
    assert record["report_record"]["report_format_version"] == 1
    assert "secret" not in record


def test_project_outcome_rejects_missing_canonical_report_record(monkeypatch) -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    transaction = Transaction(reference="acme-1")
    monkeypatch.setattr(acme_main, "generate_report", lambda transaction: SimpleNamespace(record=None))

    with pytest.raises(SystemException, match="canonical transaction report record"):
        _project_outcome(item, transaction, None)


def test_project_outcome_covers_transaction_build_failure() -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    record = _project_outcome(item, None, SystemException("build failed", action="build"))
    assert "outcome" not in record
    assert "report_record" not in record
    assert "transaction_id" not in record
    assert record["diagnostics"]["error_type"] == "system_exception"


def test_project_outcome_sanitizes_persistence_error() -> None:
    item = QueueItem(reference="acme-1", payload={"work_item_id": "1", "discovered_hash": "v1"})
    record = _project_outcome(item, None, sqlite3.OperationalError("database path details"))
    assert record["diagnostics"] == {
        "failed_skill": "",
        "error_type": "unexpected_exception",
        "message": "Unexpected item-processing error",
    }


def test_failed_summary_transaction_is_persisted(monkeypatch, example_config) -> None:
    def fail(self, ctx):
        raise SystemException("summary failed", action=self.name)

    monkeypatch.setattr("main.WriteSummary.execute", fail)
    records = [{"work_item_id": "1001", "status": "successful"}]
    with pytest.raises(SystemException, match="summary transaction failed"):
        _run_summary_transaction(
            example_config,
            Engine(max_retries=0),
            run_id="failed-summary",
            records=records,
            omitted_record_count=0,
            queue_summary=QueueRunSummary(),
            credentials=FakeCredentials(),
        )
    persisted = list_transactions(str(example_config["transaction_db_path"]), limit=10)
    assert persisted[0].reference == "acme-summary-failed-summary"
    assert persisted[0].status is Status.FAILED
    assert persisted[0].state["run_id"] == "failed-summary"
    assert persisted[0].state["records"] == records


class SkillFailure(Skill):
    def execute(self, ctx) -> None:
        return
