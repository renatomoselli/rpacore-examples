from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from rpacore import HistoryEntry, HistoryEvent, Status, Transaction

import main as checkpoint_main


def test_create_skills_returns_ordered_checkpoint_pipeline() -> None:
    skills = checkpoint_main._create_skills()

    assert [skill.name for skill in skills] == ["save_state", "fail_task"]
    assert [skill.execution_order for skill in skills] == [1, 2]


def test_log_history_logs_each_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[tuple[str, str | None, int | None]] = []

    def fake_info(message: str, event: str, skill_name: str | None, order: int | None) -> None:
        messages.append((event, skill_name, order))

    history = [
        HistoryEntry(
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            event=HistoryEvent.SKILL_STARTED,
            status=Status.IN_PROGRESS,
            retry_number=0,
            skill_name="save_state",
            skill_execution_order=1,
        )
    ]

    monkeypatch.setattr(checkpoint_main.logger, "info", fake_info)
    checkpoint_main._log_history(history)

    assert messages == [("skill_started", "save_state", 1)]


def test_save_transaction_removes_checkpoint_when_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
    sample_checkpoint_path: Path,
    sample_db_path: Path,
) -> None:
    sample_checkpoint_path.write_text("orphaned", encoding="utf-8")
    tx = Transaction(reference="tx", skills=[])

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

    monkeypatch.setattr(checkpoint_main, "load_config", lambda path: dict(config))
    monkeypatch.setattr(
        checkpoint_main,
        "resolve_config_paths",
        lambda config, keys, base_dir, root: config,
    )

    checkpoint_main.main()

    assert sample_checkpoint_path.exists()


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

    monkeypatch.setattr(checkpoint_main, "load_config", lambda path: dict(config))
    monkeypatch.setattr(
        checkpoint_main,
        "resolve_config_paths",
        lambda config, keys, base_dir, root: config,
    )
    monkeypatch.setattr(checkpoint_main, "resume_transaction", fail_resume_transaction)

    checkpoint_main.main()

    assert sample_checkpoint_path.exists()
