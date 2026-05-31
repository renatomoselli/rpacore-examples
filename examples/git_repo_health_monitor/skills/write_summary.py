from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class WriteSummary(Skill):
    """Aggregate all repo health data into a summary report.

    Reads health reports from ctx.data["repo_health_records"] (set by WriteRepoReport)
    and writes a summary JSON file alongside the JSONL output using atomic write.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_health_records = ctx.data.get("repo_health_records") or []
        output_file = ctx.data.get("output_file")
        if output_file is None:
            raise SystemException(
                "No output_file in context — main.py must set it first",
                action=self.name,
            )

        total = len(repo_health_records)
        healthy = sum(1 for r in repo_health_records if r.get("health_status") == "healthy")
        degraded = sum(1 for r in repo_health_records if r.get("health_status") == "degraded")
        unhealthy = sum(1 for r in repo_health_records if r.get("health_status") == "unhealthy")

        summary = {
            "summary": True,
            "total_repos": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "repo_details": repo_health_records,
        }

        summary_path = str(Path(output_file).with_suffix(".summary.json"))
        output_dir = str(Path(output_file).parent) or "."

        try:
            # Atomic write: write to a temp file in the same directory, then
            # os.replace() so readers never see a partial file.
            # Pattern from json_event_log_processor/skills/write_output.py:45-67
            fd, tmp_path = tempfile.mkstemp(
                dir=output_dir,
                suffix=".tmp",
                prefix=".summary_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, summary_path)
            except BaseException:
                # Clean up temp file on any failure (including KeyboardInterrupt)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info(
                "Wrote summary report to %s (%d repos: %d healthy, %d degraded, %d unhealthy)",
                summary_path,
                total,
                healthy,
                degraded,
                unhealthy,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write summary report to {summary_path}: {exc}",
                action=self.name,
            ) from exc
