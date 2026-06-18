"""Unit tests for the WriteSummary skill."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from rpacore import SystemException
from skills.write_summary import WriteSummary
from tests.conftest import make_context


class TestWriteSummary:
    """Test the WriteSummary skill."""

    def test_writes_jsonl_and_summary_json(self, tmp_path):
        """Test that WriteSummary writes the JSONL report and summary JSON atomically."""
        output_file = str(tmp_path / "health_report.jsonl")
        records = [
            {"repository": "/tmp/alpha", "health_status": "healthy", "uncommitted_changes": 0},
            {"repository": "/tmp/beta", "health_status": "degraded", "uncommitted_changes": 1},
            {"repository": "/tmp/gamma", "health_status": "unhealthy", "uncommitted_changes": 3},
        ]
        ctx = make_context(state={
            "repo_health_records": records,
            "output_file": output_file,
        })

        skill = WriteSummary("write_summary", 1)
        skill.execute(ctx)

        assert Path(output_file).exists()
        with open(output_file, encoding="utf-8") as f:
            jsonl_records = [json.loads(line) for line in f]
        assert jsonl_records == records

        summary_path = str(Path(output_file).with_suffix(".summary.json"))
        assert Path(summary_path).exists()
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["summary"] is True
        assert summary["total_repos"] == 3
        assert summary["healthy"] == 1
        assert summary["degraded"] == 1
        assert summary["unhealthy"] == 1
        assert summary["failed"] == 0
        assert summary["business_violations"] == 2
        assert summary["business_failed"] == 0
        assert summary["system_failed"] == 0
        assert summary["classification_counts"] == {}
        assert len(summary["repo_details"]) == 3
        assert list(tmp_path.glob(".jsonl_*.tmp")) == []
        assert list(tmp_path.glob(".summary_*.tmp")) == []

    def test_registers_artifacts(self, tmp_path):
        """Test that WriteSummary registers both files as transaction artifacts."""
        output_file = str(tmp_path / "health_report.jsonl")
        records = [
            {"repository": "/tmp/test", "health_status": "healthy"},
        ]
        ctx = make_context(state={
            "repo_health_records": records,
            "output_file": output_file,
        })

        skill = WriteSummary("write_summary", 1)
        skill.execute(ctx)

        assert len(ctx.transaction.artifacts) == 2
        artifact_names = [a.name for a in ctx.transaction.artifacts]
        assert "health-report-jsonl" in artifact_names
        assert "health-report-summary" in artifact_names

        jsonl_artifact = next(a for a in ctx.transaction.artifacts if a.name == "health-report-jsonl")
        assert jsonl_artifact.kind == "report"
        assert jsonl_artifact.metadata["record_count"] == 1
        assert jsonl_artifact.metadata["format"] == "jsonl"

        summary_artifact = next(a for a in ctx.transaction.artifacts if a.name == "health-report-summary")
        assert summary_artifact.kind == "summary"
        assert summary_artifact.metadata["total_repos"] == 1
        assert summary_artifact.metadata["healthy"] == 1
        assert summary_artifact.metadata["failed"] == 0
        assert summary_artifact.metadata["business_violations"] == 0
        assert summary_artifact.metadata["business_failed"] == 0
        assert summary_artifact.metadata["system_failed"] == 0
        assert summary_artifact.metadata["classification_counts"] == {}

    def test_handles_empty_records(self, tmp_path):
        """Test that WriteSummary handles empty repo_health_records gracefully."""
        output_file = str(tmp_path / "health_report.jsonl")
        ctx = make_context(state={
            "repo_health_records": [],
            "output_file": output_file,
        })

        skill = WriteSummary("write_summary", 1)
        skill.execute(ctx)

        summary_path = str(Path(output_file).with_suffix(".summary.json"))
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        assert summary["total_repos"] == 0
        assert summary["healthy"] == 0
        assert summary["degraded"] == 0
        assert summary["unhealthy"] == 0
        assert summary["failed"] == 0
        assert summary["business_violations"] == 0
        assert summary["business_failed"] == 0
        assert summary["system_failed"] == 0
        assert summary["classification_counts"] == {}
        assert Path(output_file).read_text(encoding="utf-8") == ""

    def test_counts_business_and_system_failures(self, tmp_path):
        output_file = str(tmp_path / "health_report.jsonl")
        records = [
            {"repository": "/tmp/alpha", "health_status": "healthy", "failure_type": "none", "classification": "healthy"},
            {
                "repository": "/tmp/beta",
                "health_status": "degraded",
                "failure_type": "business",
                "classification": "attention_needed",
            },
            {
                "repository": "/tmp/gamma",
                "health_status": "failed",
                "failure_type": "system",
                "classification": "technical_failure",
            },
            {
                "repository": "/tmp/delta",
                "health_status": "failed",
                "failure_type": "business",
                "classification": "technical_failure",
            },
        ]
        ctx = make_context(state={
            "repo_health_records": records,
            "output_file": output_file,
        })

        skill = WriteSummary("write_summary", 1)
        skill.execute(ctx)

        summary_path = Path(output_file).with_suffix(".summary.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["total_repos"] == 4
        assert summary["failed"] == 2
        assert summary["business_violations"] == 1
        assert summary["business_failed"] == 1
        assert summary["system_failed"] == 1
        assert summary["classification_counts"] == {
            "healthy": 1,
            "attention_needed": 1,
            "technical_failure": 2,
        }

    def test_raises_on_missing_repo_health_records(self):
        """Test that WriteSummary raises when repo_health_records is missing."""
        ctx = make_context(state={"output_file": "/tmp/test.jsonl"})
        skill = WriteSummary("write_summary", 1)
        with pytest.raises(SystemException, match="repo_health_records"):
            skill.execute(ctx)

    def test_raises_on_missing_output_file(self):
        ctx = make_context(state={"repo_health_records": []})
        skill = WriteSummary("write_summary", 1)
        with pytest.raises(SystemException, match="output_file"):
            skill.execute(ctx)

    def test_raises_on_io_error(self, tmp_path, monkeypatch):
        """Test that WriteSummary raises SystemException when os.replace fails."""
        output_file = str(tmp_path / "health_report.jsonl")
        ctx = make_context(state={
            "repo_health_records": [{"repository": "/tmp/test", "health_status": "healthy"}],
            "output_file": output_file,
        })

        def mock_replace(src, dst):
            raise OSError("Permission denied")

        monkeypatch.setattr(os, "replace", mock_replace)

        skill = WriteSummary("write_summary", 1)
        with pytest.raises(SystemException, match="Failed to write reports"):
            skill.execute(ctx)

        assert list(tmp_path.glob(".jsonl_*.tmp")) == []
        assert list(tmp_path.glob(".summary_*.tmp")) == []

    def test_second_temp_allocation_failure_cleans_first_temp(self, tmp_path, monkeypatch):
        output_file = str(tmp_path / "health_report.jsonl")
        ctx = make_context(state={
            "repo_health_records": [{"repository": "/tmp/test", "health_status": "healthy"}],
            "output_file": output_file,
        })

        real_mkstemp = tempfile.mkstemp
        calls = 0

        def mock_mkstemp(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("No space left on device")
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(tempfile, "mkstemp", mock_mkstemp)

        skill = WriteSummary("write_summary", 1)
        with pytest.raises(SystemException, match="Failed to write reports"):
            skill.execute(ctx)

        assert list(tmp_path.glob(".jsonl_*.tmp")) == []
        assert list(tmp_path.glob(".summary_*.tmp")) == []

    def test_second_replace_failure_preserves_published_jsonl(self, tmp_path, monkeypatch):
        """If summary publish fails after JSONL publish, keep the usable JSONL report."""
        output_file = str(tmp_path / "health_report.jsonl")
        records = [{"repository": "/tmp/test", "health_status": "healthy"}]
        ctx = make_context(state={
            "repo_health_records": records,
            "output_file": output_file,
        })

        real_replace = os.replace
        calls = 0

        def mock_replace(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Summary publish failed")
            real_replace(src, dst)

        monkeypatch.setattr(os, "replace", mock_replace)

        skill = WriteSummary("write_summary", 1)
        with pytest.raises(SystemException, match="Failed to write reports"):
            skill.execute(ctx)

        assert [json.loads(line) for line in Path(output_file).read_text(encoding="utf-8").splitlines()] == records
        assert not Path(output_file).with_suffix(".summary.json").exists()
        assert ctx.transaction.artifacts == []
        assert list(tmp_path.glob(".jsonl_*.tmp")) == []
        assert list(tmp_path.glob(".summary_*.tmp")) == []
