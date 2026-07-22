"""Unit tests for AppendToMaster skill."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rpacore import Engine, ProcessContext, Status, SystemException, Transaction

from skills.append_to_master import AppendToMaster


def _run(data, config):
    tx = Transaction(
        reference="append-master",
        skills=[AppendToMaster(name="append_to_master", execution_order=1)],
    )
    # Seed state from data dict
    for key, value in data.items():
        tx.state[key] = value
    ctx = ProcessContext(transaction=tx, config=config)
    Engine(max_retries=0).run(ctx)
    return tx


def _make_report(report_file="valid.csv"):
    return {
        "report_file": str(Path("/fake") / report_file),
        "processed_report": {
            "branch_id": 101,
            "date": "2024-03-01",
            "revenue": "12450.75",
            "headcount": 23,
            "revenue_per_headcount": "541.34",
        },
    }


def test_appends_row_to_new_master(tmp_path):
    master = tmp_path / "master.csv"
    tx = _run(_make_report(), {"master_csv": str(master)})
    assert tx.status == Status.SUCCESSFUL
    assert master.exists()
    with master.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["branch_id"] == "101"
    assert rows[0]["source_file"] == "valid.csv"


def test_appends_header_only_once(tmp_path):
    master = tmp_path / "master.csv"
    data1 = _make_report("a.csv")
    data2 = _make_report("b.csv")
    # Give each run its own mutable copy
    for data in (data1, data2):
        tx = _run(data, {"master_csv": str(master)})
        assert tx.status == Status.SUCCESSFUL

    with master.open(encoding="utf-8") as f:
        lines = f.readlines()
    headers = [line for line in lines if line.startswith("source_file")]
    assert len(headers) == 1
    assert not (master.parent / "master.csv.lock").exists()


def test_idempotent_by_source_file(tmp_path):
    master = tmp_path / "master.csv"
    for _ in range(3):
        tx = _run(_make_report("same.csv"), {"master_csv": str(master)})
        assert tx.status == Status.SUCCESSFUL

    with master.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


def test_master_read_error_fails_instead_of_appending_duplicate(tmp_path, monkeypatch):
    master = tmp_path / "master.csv"
    master.write_text(
        "source_file,branch_id,date,revenue,headcount,revenue_per_headcount\n"
        "same.csv,101,2024-03-01,12450.75,23,541.34\n",
        encoding="utf-8",
    )
    original_open = Path.open

    def fail_master_read(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == master and mode == "r":
            raise OSError("master is temporarily unavailable")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_master_read)

    tx = _run(_make_report("same.csv"), {"master_csv": str(master)})

    assert tx.status == Status.FAILED
    failed = tx.failed_skills()[0]
    assert isinstance(failed.exceptions[-1], SystemException)
    assert "Unable to inspect master CSV" in str(failed.exceptions[-1])

    monkeypatch.undo()
    with master.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1


def test_raises_when_no_processed_report():
    tx = _run({}, {"master_csv": "/tmp/test.csv"})
    assert tx.status == Status.FAILED
    assert "processed_report" in str(tx.failed_skills()[0].exceptions[-1])


def test_raises_when_no_master_csv_config():
    data = _make_report()
    tx = _run(data, {})
    assert tx.status == Status.FAILED
    assert "master_csv" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_path_traversal_blocked(tmp_path):
    """source_file extracted from a path outside inbox should be rejected."""
    master = tmp_path / "master.csv"
    data = {
        "report_file": str(tmp_path / ".." / "escape.csv"),
        "processed_report": {
            "branch_id": 101,
            "date": "2024-03-01",
            "revenue": "100.00",
            "headcount": 5,
            "revenue_per_headcount": "20.00",
        },
    }
    config = {"master_csv": str(master), "inbox_dir": str(tmp_path / "inbox")}
    tx = _run(data, config)
    assert tx.status == Status.FAILED
    assert "resolves outside root" in str(tx.failed_skills()[0].exceptions[-1]).lower()


def test_no_inbox_dir_skips_path_validation(tmp_path):
    """When inbox_dir is not in config, path validation is skipped."""
    master = tmp_path / "master.csv"
    tx = _run(_make_report(), {"master_csv": str(master)})
    assert tx.status == Status.SUCCESSFUL
    assert master.exists()
