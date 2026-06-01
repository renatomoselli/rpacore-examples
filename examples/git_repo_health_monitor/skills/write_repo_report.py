from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class WriteRepoReport(Skill):
    """Aggregate health check results and store in shared_data.

    Computes health_status based on failure count:
      - 0 failures → "healthy"
      - 1-2 failures → "degraded"
      - 3+ failures → "unhealthy"

    Stores ctx.data["repo_health_records"] = list of health report dicts.
    Stores ctx.data["health_report"] = latest health report dict (for compatibility).

    Note: JSONL file writing is handled by WriteSummary in batch mode.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_path = ctx.data.get("current_repo")
        if repo_path is None:
            raise SystemException(
                "No current_repo in context — main.py must set it first",
                action=self.name,
            )

        output_file = ctx.data.get("output_file")
        if output_file is None:
            raise SystemException(
                "No output_file in context — main.py must set it first",
                action=self.name,
            )

        # Collect data from upstream skills
        uncommitted_changes = ctx.data.get("uncommitted_changes", [])
        recent_commits = ctx.data.get("recent_commits", [])
        remotes = ctx.data.get("remotes", {})
        stale_branches = ctx.data.get("stale_branches", [])
        all_branches = ctx.data.get("all_branches", [])

        # Weighted failure count: uncommitted changes scale with severity (capped at 2)
        failure_count = 0
        if uncommitted_changes:
            failure_count += min(len(uncommitted_changes), 2)
        if stale_branches:
            failure_count += 1
        if not remotes:
            failure_count += 1

        # Compute health status
        if failure_count == 0:
            health_status = "healthy"
        elif failure_count <= 2:
            health_status = "degraded"
        else:
            health_status = "unhealthy"

        # Get most recent commit timestamp (recent_commits is newest-first)
        last_commit = None
        if recent_commits:
            last_commit = recent_commits[0].get("timestamp")

        health_report = {
            "repository": repo_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_status": health_status,
            "uncommitted_changes": len(uncommitted_changes),
            "recent_commits": recent_commits,
            "remotes": remotes,
            "stale_branches": stale_branches,
            "branches": all_branches,
            "last_commit": last_commit,
        }

        # Store in shared_data for batch write by WriteSummary
        # Initialize list on first call, append subsequent calls
        if "repo_health_records" not in ctx.data:
            ctx.data["repo_health_records"] = []
        ctx.data["repo_health_records"].append(health_report)

        # Also store as single dict for backwards compatibility
        ctx.data["health_report"] = health_report

        logger.info(
            "Computed health report for %s (%s)",
            Path(repo_path).name,
            health_status,
        )
