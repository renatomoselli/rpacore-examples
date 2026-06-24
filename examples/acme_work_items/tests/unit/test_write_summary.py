from __future__ import annotations

import json
from pathlib import Path

from rpacore import Status

from skills.write_summary import WriteSummary
from tests.conftest import run_skill


def test_write_summary_is_durable_atomic_and_registers_artifact(monkeypatch, example_config) -> None:
    fsync_calls: list[int] = []
    monkeypatch.setattr("skills.write_summary.os.fsync", fsync_calls.append)
    transaction = run_skill(
        WriteSummary(name="summary", execution_order=1),
        state={
            "run_id": "run-1",
            "records": [{"status": "successful"}],
            "omitted_record_count": 2,
            "queue_summary": {"processed": 3},
        },
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    destination = Path(transaction.state["summary_path"])
    assert destination.is_file()
    assert json.loads(destination.read_text(encoding="utf-8"))["omitted_record_count"] == 2
    assert transaction.artifacts[0].path == str(destination)
    assert not list(destination.parent.glob("*.tmp"))
    assert len(fsync_calls) == 1


def test_write_summary_failure_is_persistable(example_config, tmp_path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("x", encoding="utf-8")
    example_config["report_dir"] = str(blocking_file)
    transaction = run_skill(
        WriteSummary(name="summary", execution_order=1),
        state={"run_id": "run-2", "records": [], "omitted_record_count": 0, "queue_summary": {}},
        config=example_config,
    )
    assert transaction.status is Status.FAILED
