from __future__ import annotations

import json
from pathlib import Path

import pytest

from main import run_example
from tests.conftest import browser_session


pytestmark = pytest.mark.integration


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
