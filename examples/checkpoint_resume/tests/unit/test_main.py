from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from rpacore import HistoryEntry, HistoryEvent, Status, SystemException, Transaction

import main as checkpoint_main


def test_create_steps_returns_ordered_checkpoint_pipeline() -> None:
    steps = checkpoint_main._create_steps()

    assert [step.name for step in steps] == ["save_state", "fail_task"]
    assert [step.execution_order for step in steps] == [1, 2]


def test_log_history_logs_each_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[tuple[str, str | None, int | None]] = []

    def fake_info(message: str, event: str, step_name: str | None, order: int | None) -> None:
        messages.append((event, step_name, order))

    history = [
        HistoryEntry(
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            event=HistoryEvent.STEP_STARTED,
            status=Status.IN_PROGRESS,
            retry_number=0,
            step_name="save_state",
            step_execution_order=1,
        )
    ]

    monkeypatch.setattr(checkpoint_main.logger, "info", fake_info)
    checkpoint_main._log_history(history)

    assert messages == [("step_started", "save_state", 1)]


def test_save_transaction_removes_checkpoint_when_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
) -> None:
    sample_checkpoint_path.write_text("orphaned", encoding="utf-8")
    save_state = checkpoint_main._create_steps()[0]
    tx = Transaction(reference="tx", steps=[save_state])
    tx.append_history(HistoryEvent.STEP_SUCCEEDED, step=save_state)

    def fail_save_transaction(tx: Transaction, db_path: str) -> None:
        raise OSError("database unavailable")

    monkeypatch.setattr(checkpoint_main, "save_transaction", fail_save_transaction)

    with pytest.raises(OSError, match="database unavailable"):
        checkpoint_main._save_transaction(
            tx,
            str(sample_db_path),
            checkpoint_path=str(sample_checkpoint_path),
        )

    assert not sample_checkpoint_path.exists()


@pytest.mark.parametrize(
    ("step_name", "execution_order", "expected"),
    [
        (None, None, False),
        ("fail_task", 2, False),
        ("save_state", 2, False),
        ("save_state", 1, True),
    ],
)
def test_save_state_checkpoint_gate_requires_exact_success_event(
    step_name: str | None,
    execution_order: int | None,
    expected: bool,
) -> None:
    if step_name is None:
        transaction = Transaction(reference="tx")
    else:
        step_class = checkpoint_main.SaveState if step_name == "save_state" else checkpoint_main.FailTask
        step = step_class(name=step_name, execution_order=execution_order)
        transaction = Transaction(reference="tx", steps=[step])
        transaction.append_history(HistoryEvent.STEP_SUCCEEDED, step=step)

    assert checkpoint_main._is_save_state_success_checkpoint(transaction) is expected


def test_save_state_checkpoint_gate_rejects_later_history_events() -> None:
    save_state, fail_task = checkpoint_main._create_steps()
    transaction = Transaction(reference="tx", steps=[save_state, fail_task])
    transaction.append_history(HistoryEvent.STEP_SUCCEEDED, step=save_state)
    transaction.append_history(HistoryEvent.STEP_STARTED, step=fail_task)

    assert checkpoint_main._is_save_state_success_checkpoint(transaction) is False


@pytest.mark.parametrize("event", (HistoryEvent.STEP_FAILED, HistoryEvent.TRANSACTION_RESUMED))
def test_save_transaction_retains_checkpoint_after_later_or_resumed_persistence_failure(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
    event: HistoryEvent,
) -> None:
    sample_checkpoint_path.write_text("last valid checkpoint", encoding="utf-8")
    tx = Transaction(reference="tx", steps=checkpoint_main._create_steps())
    tx.append_history(event, step=tx.steps[-1] if event is HistoryEvent.STEP_FAILED else None)

    def fail_save_transaction(tx: Transaction, db_path: str) -> None:
        raise OSError("database unavailable")

    monkeypatch.setattr(checkpoint_main, "save_transaction", fail_save_transaction)

    with pytest.raises(OSError, match="database unavailable"):
        checkpoint_main._save_transaction(
            tx,
            str(sample_db_path),
            checkpoint_path=str(sample_checkpoint_path),
        )

    assert sample_checkpoint_path.read_text(encoding="utf-8") == "last valid checkpoint"


def test_load_example_config_requires_project_config_and_resolves_paths_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": "state/rpacore.db",
        "checkpoint_path": "artifacts/checkpoint.json",
        "fail_on_first_run": True,
    }
    monkeypatch.setattr(checkpoint_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint_main, "load_config", lambda path, *, require_file: dict(config))

    loaded = checkpoint_main._load_example_config()

    assert config["transaction_db_path"] == "state/rpacore.db"
    assert config["checkpoint_path"] == "artifacts/checkpoint.json"
    assert loaded["transaction_db_path"] == str(tmp_path / "state" / "rpacore.db")
    assert loaded["checkpoint_path"] == str(tmp_path / "artifacts" / "checkpoint.json")
    assert loaded["report_dir"] == str(tmp_path / "reports")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_retries", -1),
        ("log_level", "VERBOSE"),
        ("transaction_db_path", " "),
        ("checkpoint_path", " "),
        ("fail_on_first_run", 1),
    ],
)
def test_load_example_config_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
    value: object,
) -> None:
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": "rpacore.db",
        "checkpoint_path": "checkpoint.json",
        "fail_on_first_run": True,
    }
    config[key] = value
    monkeypatch.setattr(checkpoint_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(checkpoint_main, "load_config", lambda path, *, require_file: config)

    with pytest.raises(SystemException):
        checkpoint_main._load_example_config()


def test_main_completes_checkpoint_resume_smoke(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
) -> None:
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(sample_db_path),
        "checkpoint_path": str(sample_checkpoint_path),
        "fail_on_first_run": True,
    }

    monkeypatch.setattr(checkpoint_main, "PROJECT_ROOT", sample_db_path.parent)
    monkeypatch.setattr(checkpoint_main, "load_config", lambda path, *, require_file: dict(config))

    checkpoint_main.main()

    assert sample_checkpoint_path.exists()
    assert len(list((sample_db_path.parent / "reports").glob("*.report-v2.json"))) == 2


def test_main_happy_path_does_not_resume(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
) -> None:
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(sample_db_path),
        "checkpoint_path": str(sample_checkpoint_path),
        "fail_on_first_run": False,
    }

    def fail_resume_transaction(*args, **kwargs):
        raise AssertionError("resume_transaction should not be called")

    monkeypatch.setattr(checkpoint_main, "PROJECT_ROOT", sample_db_path.parent)
    monkeypatch.setattr(checkpoint_main, "load_config", lambda path, *, require_file: dict(config))
    monkeypatch.setattr(checkpoint_main, "resume_transaction", fail_resume_transaction)

    checkpoint_main.main()

    assert sample_checkpoint_path.exists()


def test_main_publishes_distinct_failed_and_resumed_report_records(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
) -> None:
    config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(sample_db_path),
        "checkpoint_path": str(sample_checkpoint_path),
        "fail_on_first_run": True,
    }
    monkeypatch.setattr(checkpoint_main, "PROJECT_ROOT", sample_db_path.parent)
    monkeypatch.setattr(checkpoint_main, "load_config", lambda path, *, require_file: dict(config))

    checkpoint_main.main()

    reports = list((sample_db_path.parent / "reports").glob("*.report-v2.json"))
    failed_path = next(path for path in reports if ".failed." in path.name)
    resumed_path = next(path for path in reports if ".resumed." in path.name)
    failed = json.loads(failed_path.read_text(encoding="utf-8"))
    resumed = json.loads(resumed_path.read_text(encoding="utf-8"))

    assert failed["report_format_version"] == resumed["report_format_version"] == 2
    assert failed["complete"] is resumed["complete"] is True
    assert failed["errors"] == resumed["errors"] == []
    assert failed["transaction"]["id"] == resumed["transaction"]["id"]
    assert failed["transaction"]["status"] == "failed"
    assert resumed["transaction"]["status"] == "successful"
    assert "transaction_resumed" not in [entry["event"] for entry in failed["history"]]
    assert "transaction_resumed" in [entry["event"] for entry in resumed["history"]]
