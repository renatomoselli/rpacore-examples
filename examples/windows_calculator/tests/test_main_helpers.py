"""Tests for Windows Calculator orchestration helpers."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from rpacore import ProcessContext, QueueItem, QueueRunSummary, SystemException, Transaction

import main
from skills.close_calculator import CloseCalculator


def test_move_failed_file_propagates_move_error(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    failed_dir = tmp_path / "failed"
    input_dir.mkdir()
    source = input_dir / "batch.csv"
    source.write_text("expression,expected_result\n2+2,4\n", encoding="utf-8")
    monkeypatch.setattr(main.shutil, "move", Mock(side_effect=OSError("disk error")))
    item = QueueItem(reference="batch", payload={"file_path": str(source)})

    with pytest.raises(SystemException, match="Failed to move"):
        main._move_failed_file(
            item,
            {"input_dir": str(input_dir), "failed_dir": str(failed_dir)},
        )


def test_move_failed_file_rejects_source_outside_input_dir(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = tmp_path / "outside.csv"
    source.write_text("expression,expected_result\n2+2,4\n", encoding="utf-8")
    item = QueueItem(reference="outside", payload={"file_path": str(source)})

    with pytest.raises(SystemException, match="outside allowed directory"):
        main._move_failed_file(
            item,
            {"input_dir": str(input_dir), "failed_dir": str(tmp_path / "failed")},
        )


def test_close_calculator_releases_runtime_resource():
    interactor = Mock()
    ctx = ProcessContext(transaction=Transaction(reference="close"), config={})
    ctx.resources["interactor"] = interactor

    CloseCalculator(name="close_calculator", execution_order=1).execute(ctx)

    interactor.close.assert_called_once_with()
    assert "interactor" not in ctx.resources


def test_summary_values_projects_all_authoritative_delivery_counters():
    summary = QueueRunSummary(
        processed=1,
        completed=2,
        failed=3,
        callback_errors=4,
        persistence_errors=5,
        lifecycle_errors=6,
        notification_errors=7,
        retry_scheduled=8,
        terminal_failed=9,
        lease_lost=10,
        transition_unknown=11,
    )

    assert main._summary_values(summary) == {
        "processed": 1,
        "completed": 2,
        "failed": 3,
        "callback_errors": 4,
        "persistence_errors": 5,
        "lifecycle_errors": 6,
        "notification_errors": 7,
        "retry_scheduled": 8,
        "terminal_failed": 9,
        "lease_lost": 10,
        "transition_unknown": 11,
    }
