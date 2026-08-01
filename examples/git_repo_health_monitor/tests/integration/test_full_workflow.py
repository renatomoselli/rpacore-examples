"""Integration tests for the full Git Repository Health Monitor workflow."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rpacore import Engine, ProcessContext, Status, Transaction, save_transaction
from main import REPOSITORY_DEFINITION_IDENTITY
from skills.check_working_tree import CheckWorkingTree
from skills.capture_recent_commits import CaptureRecentCommits
from skills.check_remotes import CheckRemotes
from skills.check_stale_branches import CheckStaleBranches
from skills.write_repo_report import WriteRepoReport
from skills.write_summary import WriteSummary


def _create_test_repo(tmpdir: Path, name: str = "test_repo", add_remote: bool = False) -> Path:
    """Create a real git repo for integration testing."""
    repo_path = Path(tmpdir) / name
    repo_path.mkdir()
    (repo_path / "README.md").write_text("Test\n")

    subprocess.run(["git", "init"], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo_path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo_path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=str(repo_path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(repo_path), check=True, capture_output=True,
    )

    if add_remote:
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/test.git"],
            cwd=str(repo_path), check=True, capture_output=True,
        )

    return repo_path


class TestFullWorkflow:
    """Integration test for the full Git health monitor workflow."""

    _config = {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": "",
        "repos": [],
        "output_file": "",
        "stale_branch_days": 30,
    }

    def test_full_workflow_produces_correct_output(self):
        """Test the full pipeline: health checks per repo, then summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "rpacore.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")
            real_repo = _create_test_repo(Path(tmpdir), add_remote=True)

            config = dict(self._config)
            config["transaction_db_path"] = db_path
            config["repos"] = [str(real_repo)]
            config["output_file"] = output_file

            engine = Engine(max_retries=0)

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                definition_identity=REPOSITORY_DEFINITION_IDENTITY,
                state={
                    "current_repo": str(real_repo),
                    "output_file": output_file,
                },
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config))
            save_transaction(repo_tx, db_path=db_path)

            assert "health_report" in repo_tx.state
            health_report = repo_tx.state["health_report"]
            assert health_report["repository"] == str(real_repo)
            assert health_report["health_status"] == "healthy"

    def test_full_workflow_with_uncommitted_changes(self):
        """Test the full pipeline detects uncommitted changes as degraded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "rpacore.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")
            real_repo = _create_test_repo(Path(tmpdir))

            # Modify a file to create uncommitted changes
            (real_repo / "README.md").write_text("Modified\n")

            config = dict(self._config)
            config["transaction_db_path"] = db_path
            config["repos"] = [str(real_repo)]
            config["output_file"] = output_file

            engine = Engine(max_retries=0)

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                definition_identity=REPOSITORY_DEFINITION_IDENTITY,
                state={
                    "current_repo": str(real_repo),
                    "output_file": output_file,
                },
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config))
            save_transaction(repo_tx, db_path=db_path)

            assert "health_report" in repo_tx.state
            # Should be degraded due to uncommitted changes + no remotes
            health_status = repo_tx.state["health_report"]["health_status"]
            assert health_status == "degraded"
            # Transaction status is FAILED because WriteRepoReport raises BusinessException
            assert repo_tx.status == Status.FAILED

    def test_full_workflow_with_no_remotes(self):
        """Test the full pipeline detects no remotes as degraded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "rpacore.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")
            real_repo = _create_test_repo(Path(tmpdir))  # no remote

            config = dict(self._config)
            config["transaction_db_path"] = db_path
            config["repos"] = [str(real_repo)]
            config["output_file"] = output_file

            engine = Engine(max_retries=0)

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                definition_identity=REPOSITORY_DEFINITION_IDENTITY,
                state={
                    "current_repo": str(real_repo),
                    "output_file": output_file,
                },
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config))
            save_transaction(repo_tx, db_path=db_path)

            assert "health_report" in repo_tx.state
            assert repo_tx.state["health_report"]["health_status"] == "degraded"
            assert repo_tx.state["health_report"]["remotes"] == {}

    def test_aggregation_path_repo_health_records(self):
        """Test that repo_health_records accumulates across repos and feeds WriteSummary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "rpacore.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            repo_a = _create_test_repo(Path(tmpdir), name="alpha", add_remote=True)
            repo_b = _create_test_repo(Path(tmpdir), name="beta")  # no remote

            config = dict(self._config)
            config["transaction_db_path"] = db_path
            config["repos"] = [str(repo_a), str(repo_b)]
            config["output_file"] = output_file

            engine = Engine(max_retries=0)

            # Simulate main.py aggregation: run per repo, accumulate
            repo_health_records = []
            for rp in [repo_a, repo_b]:
                repo_tx = Transaction(
                    reference=f"repo-{rp.name}",
                    state={
                        "current_repo": str(rp),
                        "output_file": output_file,
                    },
                    skills=[
                        CheckWorkingTree(name="check_working_tree", execution_order=1),
                        CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                        CheckRemotes(name="check_remotes", execution_order=3),
                        CheckStaleBranches(name="check_stale_branches", execution_order=4),
                        WriteRepoReport(name="write_repo_report", execution_order=5),
                    ],
                )
                engine.run(ProcessContext(transaction=repo_tx, config=config))

                if "health_report" in repo_tx.state:
                    repo_health_records.append(repo_tx.state["health_report"])

            assert len(repo_health_records) == 2
            assert repo_health_records[0]["health_status"] == "healthy"  # alpha has remote
            assert repo_health_records[1]["health_status"] == "degraded"  # beta has no remote

            # Run WriteSummary with accumulated records
            summary_tx = Transaction(
                reference="summary-report",
                state={
                    "repo_health_records": repo_health_records,
                    "output_file": output_file,
                },
                skills=[WriteSummary(name="write_summary", execution_order=1)],
            )
            engine.run(ProcessContext(transaction=summary_tx, config=config))

            summary_path = str(Path(output_file).with_suffix(".summary.json"))
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)

            assert summary["total_repos"] == 2
            assert summary["healthy"] == 1
            assert summary["degraded"] == 1
            assert summary["unhealthy"] == 0

            with open(output_file, encoding="utf-8") as f:
                jsonl_records = [json.loads(line) for line in f]

            assert len(jsonl_records) == 2
            assert [record["repo_name"] for record in jsonl_records] == ["alpha", "beta"]
