"""Integration tests for the full Git Repository Health Monitor workflow."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add parent directory to path for importing skills
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from oref import Engine, ProcessContext, Status, Transaction, save_transaction
from skills.check_working_tree import CheckWorkingTree
from skills.capture_recent_commits import CaptureRecentCommits
from skills.check_remotes import CheckRemotes
from skills.check_stale_branches import CheckStaleBranches
from skills.write_repo_report import WriteRepoReport
from skills.write_summary import WriteSummary


class TestFullWorkflow:
    """Integration test for the full Git health monitor workflow."""

    def test_full_workflow_produces_correct_output(self):
        """Test the full pipeline: health checks per repo, then summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "oref.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            # Create a real git repo for testing
            real_repo = Path(tmpdir) / "test_repo"
            real_repo.mkdir()
            (real_repo / "README.md").write_text("Test\n")
            subprocess.run(["git", "init"], cwd=str(real_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/example/test.git"],
                cwd=str(real_repo), check=True, capture_output=True,
            )

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "repos": [str(real_repo)],
                "output_file": output_file,
                "stale_branch_days": 30,
            }

            engine = Engine(max_retries=0)

            # Set up context for this repo
            shared_data["current_repo"] = str(real_repo)
            shared_data["output_file"] = output_file

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))
            save_transaction(repo_tx, db_path=db_path)

            assert repo_tx.status == Status.SUCCESSFUL
            assert "health_report" in shared_data
            health_report = shared_data["health_report"]
            assert health_report["repository"] == str(real_repo)
            assert health_report["health_status"] == "healthy"

            # Verify health report stored in shared_data
            records = shared_data["repo_health_records"]
            assert len(records) == 1
            assert records[0]["health_status"] == "healthy"
            assert records[0]["repository"] == str(real_repo)

    def test_full_workflow_with_uncommitted_changes(self):
        """Test the full pipeline detects uncommitted changes as degraded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "oref.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            # Create a real git repo
            real_repo = Path(tmpdir) / "test_repo"
            real_repo.mkdir()
            (real_repo / "README.md").write_text("Test\n")
            subprocess.run(["git", "init"], cwd=str(real_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=str(real_repo), check=True, capture_output=True,
            )

            # Modify a file to create uncommitted changes
            (real_repo / "README.md").write_text("Modified\n")

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "repos": [str(real_repo)],
                "output_file": output_file,
                "stale_branch_days": 30,
            }

            engine = Engine(max_retries=0)

            shared_data["current_repo"] = str(real_repo)
            shared_data["output_file"] = output_file

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))
            save_transaction(repo_tx, db_path=db_path)

            assert repo_tx.status == Status.SUCCESSFUL
            assert "health_report" in shared_data
            assert shared_data["health_report"]["health_status"] == "degraded"

    def test_full_workflow_with_no_remotes(self):
        """Test the full pipeline detects no remotes as degraded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "oref.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            # Create a real git repo without any remotes
            real_repo = Path(tmpdir) / "test_repo"
            real_repo.mkdir()
            (real_repo / "README.md").write_text("Test\n")
            subprocess.run(["git", "init"], cwd=str(real_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            # No remotes added — should be degraded

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "repos": [str(real_repo)],
                "output_file": output_file,
                "stale_branch_days": 30,
            }

            engine = Engine(max_retries=0)

            shared_data["current_repo"] = str(real_repo)
            shared_data["output_file"] = output_file

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))
            save_transaction(repo_tx, db_path=db_path)

            assert repo_tx.status == Status.SUCCESSFUL
            assert "health_report" in shared_data
            assert shared_data["health_report"]["health_status"] == "degraded"
            assert shared_data["health_report"]["remotes"] == {}

    def test_full_workflow_writes_summary(self):
        """Test that WriteSummary produces a valid summary JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "oref.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            # Create a real git repo
            real_repo = Path(tmpdir) / "test_repo"
            real_repo.mkdir()
            (real_repo / "README.md").write_text("Test\n")
            subprocess.run(["git", "init"], cwd=str(real_repo), check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(real_repo), check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=str(real_repo), check=True, capture_output=True,
            )

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "repos": [str(real_repo)],
                "output_file": output_file,
                "stale_branch_days": 30,
            }

            engine = Engine(max_retries=0)

            shared_data["current_repo"] = str(real_repo)
            shared_data["output_file"] = output_file

            repo_tx = Transaction(
                reference=f"repo-{real_repo.name}",
                skills=[
                    CheckWorkingTree(name="check_working_tree", execution_order=1),
                    CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                    CheckRemotes(name="check_remotes", execution_order=3),
                    CheckStaleBranches(name="check_stale_branches", execution_order=4),
                    WriteRepoReport(name="write_repo_report", execution_order=5),
                ],
            )
            engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))
            save_transaction(repo_tx, db_path=db_path)

            assert repo_tx.status == Status.SUCCESSFUL
            assert "health_report" in shared_data
            health_report = shared_data["health_report"]
            assert health_report["repository"] == str(real_repo)
            assert health_report["health_status"] == "degraded"

            # WriteRepoReport stores in shared_data, no manual append needed
            assert "repo_health_records" in shared_data
            assert len(shared_data["repo_health_records"]) == 1

            # Now run WriteSummary with the records from WriteRepoReport
            summary_tx = Transaction(
                reference="summary-report",
                skills=[
                    WriteSummary(name="write_summary", execution_order=1),
                ],
            )
            engine.run(ProcessContext(transaction=summary_tx, config=config, data=shared_data))
            save_transaction(summary_tx, db_path=db_path)

            assert summary_tx.status == Status.SUCCESSFUL

            # Verify summary file was created
            summary_path = str(Path(output_file).with_suffix(".summary.json"))
            assert Path(summary_path).exists()

            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)

            assert summary["summary"] is True
            assert summary["total_repos"] == 1
            assert summary["healthy"] == 0
            assert summary["degraded"] == 1
            assert summary["unhealthy"] == 0
            assert len(summary["repo_details"]) == 1

    def test_aggregation_path_repo_health_records(self):
        """Test that repo_health_records accumulates across repos and feeds WriteSummary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "oref.db")
            output_file = str(Path(tmpdir) / "health_report.jsonl")

            # Create two real git repos
            repo_a = Path(tmpdir) / "alpha"
            repo_a.mkdir()
            (repo_a / "README.md").write_text("A\n")
            subprocess.run(["git", "init"], cwd=str(repo_a), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo_a), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo_a), check=True, capture_output=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo_a), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_a), check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", "https://example.com/a.git"], cwd=str(repo_a), check=True, capture_output=True)

            repo_b = Path(tmpdir) / "beta"
            repo_b.mkdir()
            (repo_b / "README.md").write_text("B\n")
            subprocess.run(["git", "init"], cwd=str(repo_b), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo_b), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo_b), check=True, capture_output=True)
            subprocess.run(["git", "add", "README.md"], cwd=str(repo_b), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_b), check=True, capture_output=True)
            # No remote for beta

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "repos": [str(repo_a), str(repo_b)],
                "output_file": output_file,
                "stale_branch_days": 30,
            }

            engine = Engine(max_retries=0)

            # Simulate main.py aggregation: run WriteRepoReport for each repo
            repo_health_records = []
            for rp in [repo_a, repo_b]:
                shared_data.clear()
                shared_data["current_repo"] = str(rp)
                shared_data["output_file"] = output_file

                repo_tx = Transaction(
                    reference=f"repo-{rp.name}",
                    skills=[
                        CheckWorkingTree(name="check_working_tree", execution_order=1),
                        CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                        CheckRemotes(name="check_remotes", execution_order=3),
                        CheckStaleBranches(name="check_stale_branches", execution_order=4),
                        WriteRepoReport(name="write_repo_report", execution_order=5),
                    ],
                )
                engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))

                # Explicit key-checking (main.py pattern)
                if "health_report" in shared_data:
                    repo_health_records.append(shared_data["health_report"])

            assert len(repo_health_records) == 2
            assert repo_health_records[0]["health_status"] == "healthy"  # alpha has remote
            assert repo_health_records[1]["health_status"] == "degraded"  # beta has no remote

            # Run WriteSummary with accumulated records
            shared_data.clear()
            shared_data["output_file"] = output_file
            shared_data["repo_health_records"] = repo_health_records

            summary_tx = Transaction(
                reference="summary-report",
                skills=[WriteSummary(name="write_summary", execution_order=1)],
            )
            engine.run(ProcessContext(transaction=summary_tx, config=config, data=shared_data))

            summary_path = str(Path(output_file).with_suffix(".summary.json"))
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)

            assert summary["total_repos"] == 2
            assert summary["healthy"] == 1
            assert summary["degraded"] == 1
            assert summary["unhealthy"] == 0
