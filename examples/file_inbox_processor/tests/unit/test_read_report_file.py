"""Unit tests for ReadReportFile skill."""

from __future__ import annotations

import pytest

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.read_report_file import ReadReportFile


def _run(data, config=None):
    tx = Transaction(
        reference="read-report",
        skills=[ReadReportFile(name="read_report_file", execution_order=1)],
    )
    ctx = ProcessContext(transaction=tx, config=config or {})
    # Seed state from data dict
    for key, value in data.items():
        tx.state[key] = value
    Engine(max_retries=0).run(ctx)
    return tx


def test_reads_valid_csv(tmp_path):
    csv_file = tmp_path / "inbox" / "branch_101.csv"
    csv_file.parent.mkdir()
    csv_file.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,12450.75,23\n",
        encoding="utf-8",
    )
    config = {"inbox_dir": str(tmp_path / "inbox")}
    tx = _run(
        {"file_path": str(csv_file)},
        config=config,
    )
    assert tx.status == Status.SUCCESSFUL
    assert len(tx.state["report_rows"]) == 1
    assert tx.state["report_rows"][0]["branch_id"] == "101"
    assert tx.state["report_columns"] == ["branch_id", "date", "revenue", "headcount"]
    assert tx.state["report_file"] == str(csv_file)


def test_missing_file_path_raises():
    tx = _run({})
    assert tx.status == Status.FAILED
    failed = tx.failed_skills()[0]
    assert "file_path" in str(failed.exceptions[-1]).lower()


def test_empty_file_path_raises():
    tx = _run({"file_path": ""})
    assert tx.status == Status.FAILED


def test_file_not_found_raises(tmp_path):
    config = {"inbox_dir": str(tmp_path)}
    tx = _run(
        {"file_path": str(tmp_path / "nonexistent.csv")},
        config=config,
    )
    assert tx.status == Status.FAILED
    assert "Unable to read report file" in str(tx.failed_skills()[0].exceptions[-1])


def test_empty_csv(tmp_path):
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("", encoding="utf-8")
    tx = _run({"file_path": str(csv_file)})
    assert tx.status == Status.SUCCESSFUL
    assert tx.state["report_rows"] == []
    assert tx.state["report_columns"] == []


def test_path_traversal_blocked(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("sensitive data", encoding="utf-8")

    config = {"inbox_dir": str(inbox)}
    tx = _run(
        {"file_path": str(outside)},
        config=config,
    )
    assert tx.status == Status.FAILED
    failed = tx.failed_skills()[0]
    assert "outside allowed directory" in str(failed.exceptions[-1]).lower()


def test_symlink_escape_blocked(tmp_path):
    """Symlink pointing outside inbox should be blocked."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive", encoding="utf-8")
    link = inbox / "escape.csv"
    try:
        link.symlink_to(secret)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires elevated privileges")
        raise

    config = {"inbox_dir": str(inbox)}
    tx = _run(
        {"file_path": str(link)},
        config=config,
    )
    assert tx.status == Status.FAILED
    assert "outside allowed directory" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_no_inbox_dir_skips_validation(tmp_path):
    """When inbox_dir is not in config, path validation is skipped."""
    csv_file = tmp_path / "report.csv"
    csv_file.write_text(
        "branch_id,date,revenue,headcount\n101,2024-03-01,100.00,5\n",
        encoding="utf-8",
    )
    tx = _run({"file_path": str(csv_file)})
    assert tx.status == Status.SUCCESSFUL
    assert len(tx.state["report_rows"]) == 1
