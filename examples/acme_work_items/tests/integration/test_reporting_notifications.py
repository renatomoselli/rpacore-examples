from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rpacore import configure_logger

import main as acme_main
from main import run_example
from tests.conftest import browser_session


pytestmark = pytest.mark.integration


SUMMARY_FIELDS = (
    "processed",
    "completed",
    "failed",
    "callback_errors",
    "persistence_errors",
    "lifecycle_errors",
    "notification_errors",
    "retry_scheduled",
    "terminal_failed",
    "lease_lost",
    "transition_unknown",
)
PROTECTED_ENVELOPE_FIELDS = {
    "log_format_version",
    "timestamp",
    "severity",
    "logger",
    "event",
    "message",
}


class RecordingNotifier:
    def __init__(self) -> None:
        self.reports = []

    def send(self, report) -> None:
        self.reports.append(report)


class FailingNotifier:
    def send(self, report) -> None:
        raise RuntimeError("offline")


def test_bounded_report_and_fake_notifications(
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    acme_server.state.add_item("1002", client_id="C-2", wiid="WI-2")
    example_config["report_max_records"] = 1
    notifier = RecordingNotifier()

    result = run_example(
        example_config,
        credentials=credentials,
        session_factory=browser_session,
        notifiers=[notifier],
    )

    assert len(notifier.reports) == 2
    report = json.loads(Path(result.summary_transaction.state["summary_path"]).read_text(encoding="utf-8"))
    assert report["record_count"] == 1
    assert report["omitted_record_count"] == 1
    assert report["queue_summary"]["notification_errors"] == 0


def test_committed_config_builds_no_notifiers() -> None:
    from rpacore import EnvCredentialProvider, build_notifiers, load_config

    config = load_config(Path(__file__).resolve().parents[2] / "config.toml", require_file=True)
    assert build_notifiers(config, EnvCredentialProvider()) == []


def test_notifier_failure_is_counted_without_changing_item_outcome(
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    result = run_example(
        example_config,
        credentials=credentials,
        session_factory=browser_session,
        notifiers=[FailingNotifier()],
    )
    assert result.queue_summary.completed == 1
    assert result.queue_summary.notification_errors == 1


def test_json_v3_logs_runner_correlation_and_canonical_summary(
    example_config,
    acme_server,
    credentials,
) -> None:
    acme_server.state.add_item("1001", client_id="C-1", wiid="WI-1")
    stream = io.StringIO()
    configure_logger(level="INFO", fmt="json", stream=stream)

    result = run_example(
        example_config,
        credentials=credentials,
        session_factory=browser_session,
    )
    acme_main._log_run_summary(result)

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert records
    assert all(record["log_format_version"] == 3 for record in records)
    assert all(PROTECTED_ENVELOPE_FIELDS <= record.keys() for record in records)
    assert all(PROTECTED_ENVELOPE_FIELDS.isdisjoint(record["attributes"]) for record in records)
    assert str(example_config["transaction_db_path"]) not in stream.getvalue()

    step_started = next(record for record in records if record["event"] == "rpacore.step.started")
    correlation = step_started["attributes"]
    assert correlation["worker_id"].startswith("acme-")
    assert correlation["queue_item_id"]
    assert correlation["queue_reference"] == "acme-1001"
    assert correlation["transaction_id"]
    assert correlation["transaction_reference"] == "acme-1001"
    assert correlation["step_name"] == "fetch_work_item"
    assert correlation["step_execution_order"] == 1
    assert correlation["retry_count"] == 0
    assert "attempt_number" not in correlation

    summary = next(record for record in records if record["event"] == "rpacore.acme.run.summary")
    attributes = summary["attributes"]
    assert {field: attributes[field] for field in SUMMARY_FIELDS} == {
        field: getattr(result.queue_summary, field) for field in SUMMARY_FIELDS
    }
    assert attributes["run_id"] == result.run_id
    assert attributes["summary_transaction_id"] == result.summary_transaction.id
    assert attributes["summary_transaction_reference"] == result.summary_transaction.reference
    assert "attempt_number" not in attributes
