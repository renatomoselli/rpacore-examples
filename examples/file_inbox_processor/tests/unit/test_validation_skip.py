"""Unit tests for validation-failure skip paths."""

from __future__ import annotations

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.append_to_master import AppendToMaster
from skills.compute_derived_fields import ComputeDerivedFields
from skills.move_file import MoveFile


def _run(skill, state, config=None):
    tx = Transaction(reference="validation-skip", skills=[skill])
    for key, value in state.items():
        tx.state[key] = value
    Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config or {}))
    return tx


def test_compute_derived_fields_skips_when_validation_failed():
    tx = _run(
        ComputeDerivedFields(name="compute_derived_fields", execution_order=1),
        {"validation_failed": True},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.skills[0].status == Status.SKIPPED
    assert "processed_report" not in tx.state


def test_append_to_master_skips_when_validation_failed(tmp_path):
    master = tmp_path / "master.csv"
    tx = _run(
        AppendToMaster(name="append_to_master", execution_order=1),
        {"validation_failed": True},
        {"master_csv": str(master)},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.skills[0].status == Status.SKIPPED
    assert not master.exists()


def test_move_file_skips_when_validation_failed(tmp_path):
    src = tmp_path / "report.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    tx = _run(
        MoveFile(name="move_file", execution_order=1),
        {"validation_failed": True, "report_file": str(src)},
        {"done_dir": str(tmp_path / "done")},
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.skills[0].status == Status.SKIPPED
    assert src.exists()
    assert "moved_file" not in tx.state
