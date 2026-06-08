from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

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
            # --- JSONL file (one line per repo health record) ---
            jsonl_path = output_file
            jsonl_dir = str(Path(jsonl_path).parent) or "."

            # Build lines: each health record as a JSON line
            jsonl_lines = [json.dumps(record, ensure_ascii=False) for record in repo_health_records]

            fd, tmp_jsonl = tempfile.mkstemp(
                dir=jsonl_dir,
                suffix=".tmp",
                prefix=".jsonl_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    for line in jsonl_lines:
                        f.write(line + "\n")
                os.replace(tmp_jsonl, jsonl_path)
            except BaseException:
                try:
                    os.unlink(tmp_jsonl)
                except OSError:
                    pass
                raise

            # --- Summary JSON (atomic write) ---
            summary_path = str(Path(output_file).with_suffix(".summary.json"))

            fd, tmp_summary = tempfile.mkstemp(
                dir=output_dir,
                suffix=".tmp",
                prefix=".summary_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                os.replace(tmp_summary, summary_path)
            except BaseException:
                try:
                    os.unlink(tmp_summary)
                except OSError:
                    pass
                raise

            logger.info(
                "Wrote JSONL report to %s and summary to %s (%d repos: %d healthy, %d degraded, %d unhealthy)",
                jsonl_path,
                summary_path,
                total,
                healthy,
                degraded,
                unhealthy,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write reports: {exc}",
                action=self.name,
            ) from exc
