from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class WriteSummary(Skill):
    """Aggregate all repo health data into a summary report.

    Reads health reports from ctx.state["repo_health_records"] (seeded by main.py
    before running this transaction) and writes a summary JSON file alongside the
    JSONL output using atomic write. Registers output files as transaction artifacts.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_health_records = ctx.require_state("repo_health_records", list, action=self.name)
        output_file = ctx.require_state("output_file", str, action=self.name)

        total = len(repo_health_records)
        healthy = sum(1 for r in repo_health_records if r.get("health_status") == "healthy")
        degraded = sum(1 for r in repo_health_records if r.get("health_status") == "degraded")
        unhealthy = sum(1 for r in repo_health_records if r.get("health_status") == "unhealthy")
        failed = sum(1 for r in repo_health_records if r.get("health_status") == "failed")
        system_failed = sum(1 for r in repo_health_records if r.get("failure_type") == "system")
        business_failed = sum(1 for r in repo_health_records if r.get("failure_type") == "business")

        summary = {
            "summary": True,
            "total_repos": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "failed": failed,
            "business_failed": business_failed,
            "system_failed": system_failed,
            "repo_details": repo_health_records,
        }

        output_dir = str(Path(output_file).parent) or "."

        try:
            jsonl_path = output_file
            jsonl_dir = str(Path(jsonl_path).parent) or "."
            summary_path = str(Path(output_file).with_suffix(".summary.json"))

            jsonl_lines = [json.dumps(record, ensure_ascii=False) for record in repo_health_records]

            jsonl_fd, tmp_jsonl = tempfile.mkstemp(
                dir=jsonl_dir,
                suffix=".tmp",
                prefix=".jsonl_",
            )
            os.close(jsonl_fd)
            summary_fd, tmp_summary = tempfile.mkstemp(
                dir=output_dir,
                suffix=".tmp",
                prefix=".summary_",
            )
            os.close(summary_fd)
            try:
                with open(tmp_jsonl, "w", encoding="utf-8") as f:
                    for line in jsonl_lines:
                        f.write(line + "\n")
                with open(tmp_summary, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
            except Exception:
                for path in (tmp_jsonl, tmp_summary):
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                    except OSError:
                        pass
                raise

            try:
                os.replace(tmp_jsonl, jsonl_path)
                os.replace(tmp_summary, summary_path)
            except Exception:
                for path in (tmp_jsonl, tmp_summary, jsonl_path):
                    try:
                        if os.path.exists(path):
                            os.unlink(path)
                    except OSError:
                        pass
                raise

            ctx.add_artifact(
                name="health-report-jsonl",
                path=jsonl_path,
                kind="report",
                metadata={
                    "example": "git_repo_health_monitor",
                    "format": "jsonl",
                    "record_count": total,
                },
            )
            # Register summary artifact
            ctx.add_artifact(
                name="health-report-summary",
                path=summary_path,
                kind="summary",
                metadata={
                    "total_repos": total,
                    "healthy": healthy,
                    "degraded": degraded,
                    "unhealthy": unhealthy,
                    "failed": failed,
                    "business_failed": business_failed,
                    "system_failed": system_failed,
                },
            )

            logger.info(
                "Wrote JSONL report to %s and summary to %s (%d repos: %d healthy, %d degraded, %d unhealthy, %d system failed)",
                jsonl_path,
                summary_path,
                total,
                healthy,
                degraded,
                unhealthy,
                system_failed,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write reports: {exc}",
                action=self.name,
            ) from exc
