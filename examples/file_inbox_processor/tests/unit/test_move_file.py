"""Unit tests for MoveFile skill."""

from __future__ import annotations

import pytest

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.move_file import MoveFile


def _run(data, config):
    tx = Transaction(
        reference="move-file",
        skills=[MoveFile(name="move_file", execution_order=1)],
    )
    # Seed state from data dict
    for key, value in data.items():
        tx.state[key] = value
    ctx = ProcessContext(transaction=tx, config=config)
    Engine(max_retries=0).run(ctx)
    return tx


def test_moves_file_to_done(tmp_path):
    src = tmp_path / "inbox" / "report.csv"
    src.parent.mkdir()
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    done_dir = tmp_path / "done"

    tx = _run(
        {"report_file": str(src)},
        {"done_dir": str(done_dir), "inbox_dir": str(tmp_path / "inbox")},
    )
    assert tx.status == Status.SUCCESSFUL
    assert not src.exists()
    assert (done_dir / "report.csv").exists()
    assert tx.state["moved_file"] == str(done_dir / "report.csv")


def test_raises_when_no_source(tmp_path):
    tx = _run(
        {},
        {"done_dir": str(tmp_path / "done")},
    )
    assert tx.status == Status.FAILED
    assert "No source file available" in str(tx.failed_skills()[0].exceptions[-1])


def test_raises_when_no_done_dir(tmp_path):
    src = tmp_path / "report.csv"
    src.write_text("a,b\n", encoding="utf-8")

    tx = _run(
        {"report_file": str(src)},
        {},
    )
    assert tx.status == Status.FAILED
    assert "done_dir" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_path_traversal_blocked(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive", encoding="utf-8")
    done_dir = tmp_path / "done"

    tx = _run(
        {"report_file": str(secret)},
        {"done_dir": str(done_dir), "inbox_dir": str(inbox)},
    )
    assert tx.status == Status.FAILED
    assert "resolves outside root" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_falls_back_to_file_path(tmp_path):
    """When report_file is absent, uses file_path as fallback."""
    src = tmp_path / "inbox" / "report.csv"
    src.parent.mkdir()
    src.write_text("a,b\n", encoding="utf-8")
    done_dir = tmp_path / "done"

    tx = _run(
        {"file_path": str(src)},
        {"done_dir": str(done_dir), "inbox_dir": str(tmp_path / "inbox")},
    )
    assert tx.status == Status.SUCCESSFUL
    assert not src.exists()
    assert (done_dir / "report.csv").exists()


def test_no_inbox_dir_skips_validation(tmp_path):
    """When inbox_dir is not in config, path validation is skipped."""
    src = tmp_path / "report.csv"
    src.write_text("a,b\n", encoding="utf-8")
    done_dir = tmp_path / "done"

    tx = _run(
        {"report_file": str(src)},
        {"done_dir": str(done_dir)},
    )
    assert tx.status == Status.SUCCESSFUL
    assert not src.exists()
    assert (done_dir / "report.csv").exists()
