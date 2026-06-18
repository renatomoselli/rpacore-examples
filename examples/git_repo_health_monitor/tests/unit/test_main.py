from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import main as workflow
from rpacore import Status, SystemException


def _config(tmp_path: Path, repos: list[Path]) -> dict[str, object]:
    return {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": str(tmp_path / "rpacore.db"),
        "repos": [str(repo) for repo in repos],
        "output_file": str(tmp_path / "health_report.jsonl"),
        "stale_branch_days": 30,
    }


def test_validate_config_rejects_missing_keys(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path, [repo])
    del config["output_file"]

    with pytest.raises(SystemException, match="Missing required config key: output_file"):
        workflow._validate_config(config)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("max_retries", "two", "must be int"),
        ("max_retries", -1, "must be >= 0"),
        ("stale_branch_days", 0, "must be > 0"),
        ("log_level", "TRACE", "must be one of"),
        ("repos", [], "must be a non-empty list"),
        ("repos", [""], "contains empty or invalid path"),
    ],
)
def test_validate_config_rejects_invalid_values(tmp_path, key, value, message):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path, [repo])
    config[key] = value

    with pytest.raises(SystemException, match=message):
        workflow._validate_config(config)


def test_validate_config_rejects_missing_repo_directory(tmp_path):
    config = _config(tmp_path, [tmp_path / "missing"])

    with pytest.raises(SystemException, match="path does not exist"):
        workflow._validate_config(config)


def test_uses_default_sample_repos_only_for_exact_default_list():
    assert workflow._uses_default_sample_repos({"repos": list(workflow.DEFAULT_SAMPLE_REPOS)}) is True
    assert workflow._uses_default_sample_repos({"repos": ["sample_repos/beta", "sample_repos/alpha"]}) is False
    assert workflow._uses_default_sample_repos({"repos": [str(Path("sample_repos/alpha"))]}) is False


def test_resolve_repo_path_handles_relative_absolute_and_home_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "PROJECT_ROOT", tmp_path)

    relative = workflow._resolve_repo_path("repo")
    absolute = workflow._resolve_repo_path(str(tmp_path / "absolute"))
    home = workflow._resolve_repo_path("~/repo")

    assert relative == str((tmp_path / "repo").resolve())
    assert absolute == str((tmp_path / "absolute").resolve())
    assert home == str((Path.home() / "repo").resolve())


def test_validate_config_rejects_output_paths_outside_project_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path, [repo])
    config["output_file"] = "../outside.jsonl"

    with pytest.raises(SystemException, match="output_file resolves outside root"):
        workflow._validate_config(config)


def test_main_validates_default_config_before_preparing_samples(tmp_path, monkeypatch):
    config = _config(tmp_path, [tmp_path / "sample_repos" / "alpha"])
    config["repos"] = list(workflow.DEFAULT_SAMPLE_REPOS)
    config["max_retries"] = -1
    prepared = False

    def prepare_sample_repos(path):
        nonlocal prepared
        prepared = True

    monkeypatch.setattr(workflow, "load_config", lambda path: dict(config))
    monkeypatch.setattr(workflow, "prepare_sample_repos", prepare_sample_repos)

    with pytest.raises(SystemException, match="max_retries"):
        workflow.main()

    assert prepared is False


def test_failed_repo_record_preserves_system_failure_details(tmp_path):
    repo_path = str(tmp_path / "repo")
    failed_skill = SimpleNamespace(
        name="check_working_tree",
        exceptions=[SystemException("git status failed", action="check_working_tree")],
    )
    repo_tx = SimpleNamespace(
        status=Status.FAILED,
        state={"uncommitted_changes": ["dirty.txt"]},
        failed_skills=lambda: [failed_skill],
    )

    record = workflow._failed_repo_record(repo_path, repo_tx)

    assert record["health_status"] == "failed"
    assert record["failure_type"] == "system"
    assert record["classification"] == "technical_failure"
    assert record["failed_skill"] == "check_working_tree"
    assert record["uncommitted_changes"] == 1


def test_main_preserves_reports_when_summary_save_fails(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _config(tmp_path, [repo])
    output_file = Path(config["output_file"])
    summary_file = output_file.with_suffix(".summary.json")

    class FakeEngine:
        def __init__(self, max_retries):
            self.max_retries = max_retries

        def run(self, ctx):
            tx = ctx.transaction
            tx.status = Status.SUCCESSFUL
            if tx.reference.startswith("repo-"):
                tx.state["health_report"] = {
                    "repository": tx.state["current_repo"],
                    "repo_name": Path(tx.state["current_repo"]).name,
                    "health_status": "healthy",
                }
            else:
                tx.skills[0].execute(ctx)

    def fail_summary_save(tx, *, db_path):
        if tx.reference == "summary-report":
            raise sqlite3.Error("summary db locked")

    monkeypatch.setattr(workflow, "load_config", lambda path: dict(config))
    monkeypatch.setattr(workflow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(workflow, "Engine", FakeEngine)
    monkeypatch.setattr(workflow, "save_transaction", fail_summary_save)

    workflow.main()

    assert output_file.exists()
    assert summary_file.exists()


def test_main_continues_after_repo_save_failure(tmp_path, monkeypatch):
    repos = [tmp_path / "alpha", tmp_path / "beta"]
    for repo in repos:
        repo.mkdir()
    config = _config(tmp_path, repos)
    output_file = Path(config["output_file"])

    class FakeEngine:
        def __init__(self, max_retries):
            self.max_retries = max_retries

        def run(self, ctx):
            tx = ctx.transaction
            tx.status = Status.SUCCESSFUL
            if tx.reference.startswith("repo-"):
                repo_path = tx.state["current_repo"]
                tx.state["health_report"] = {
                    "repository": repo_path,
                    "repo_name": Path(repo_path).name,
                    "health_status": "healthy",
                }
            else:
                tx.skills[0].execute(ctx)

    def save_with_first_repo_failure(tx, *, db_path):
        if tx.reference == "repo-alpha":
            raise sqlite3.Error("repo db locked")

    monkeypatch.setattr(workflow, "load_config", lambda path: dict(config))
    monkeypatch.setattr(workflow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(workflow, "Engine", FakeEngine)
    monkeypatch.setattr(workflow, "save_transaction", save_with_first_repo_failure)

    workflow.main()

    records = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["repo_name"] for record in records] == ["alpha", "beta"]
    assert records[0]["persistence_status"] == "failed"
    assert records[0]["persistence_error"] == "repo db locked"
    assert records[1]["persistence_status"] == "saved"


def test_main_records_non_failed_transactions_without_health_report(tmp_path, monkeypatch):
    repo = tmp_path / "skipped"
    repo.mkdir()
    config = _config(tmp_path, [repo])
    output_file = Path(config["output_file"])

    class FakeEngine:
        def __init__(self, max_retries):
            self.max_retries = max_retries

        def run(self, ctx):
            tx = ctx.transaction
            if tx.reference.startswith("repo-"):
                tx.status = Status.SKIPPED
            else:
                tx.skills[0].execute(ctx)

    monkeypatch.setattr(workflow, "load_config", lambda path: dict(config))
    monkeypatch.setattr(workflow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(workflow, "Engine", FakeEngine)
    monkeypatch.setattr(workflow, "save_transaction", lambda tx, *, db_path: None)

    workflow.main()

    records = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["repo_name"] == "skipped"
    assert records[0]["health_status"] == "failed"
    assert records[0]["error"] == str(Status.SKIPPED)
