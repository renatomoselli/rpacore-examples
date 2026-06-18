from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rpacore import BusinessException, ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class WriteRepoReport(Skill):
    """Aggregate health check results and store in state.

    Computes health_status based on failure count:
      - 0 failures \u2192 "healthy"
      - 1-2 failures \u2192 "degraded"
      - 3+ failures \u2192 "unhealthy"

    Stores ctx.state["health_report"] = latest health report dict.

    Raises BusinessException(stop=True) for "degraded" and "unhealthy" repos
    \u2014 signals business rule violation while preserving health data in state.

    Note: JSONL and summary file writing is handled by WriteSummary.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_path = ctx.require_state("current_repo", str, action=self.name)
        ctx.require_state("output_file", str, action=self.name)  # verify present, not needed locally

        # Collect data from upstream skills using optional_state with defaults
        uncommitted_changes = ctx.optional_state("uncommitted_changes", list, [], action=self.name)
        recent_commits = ctx.optional_state("recent_commits", list, [], action=self.name)
        remotes = ctx.optional_state("remotes", dict, {}, action=self.name)
        stale_branches = ctx.optional_state("stale_branches", list, [], action=self.name)
        all_branches = ctx.optional_state("all_branches", list, [], action=self.name)

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
            if last_commit is None:
                logger.warning(
                    "Most recent commit for %s is missing a timestamp",
                    Path(repo_path).name,
                )
                last_commit = "unknown"

        health_report = {
            "repository": repo_path,
            "repo_name": Path(repo_path).name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_status": health_status,
            "failure_type": "business" if health_status in ("degraded", "unhealthy") else "none",
            "classification": "business_rule_violation" if health_status in ("degraded", "unhealthy") else "ok",
            "failed_skill": "",
            "error": "",
            "uncommitted_changes": len(uncommitted_changes),
            "recent_commits": recent_commits,
            "remotes": remotes,
            "stale_branches": stale_branches,
            "branches": all_branches,
            "last_commit": last_commit,
        }

        # Store in durable state (preserved even if BusinessException is raised below)
        ctx.state["health_report"] = health_report
        ctx.transaction.metadata["repo_name"] = Path(repo_path).name
        ctx.transaction.metadata["repo_path"] = repo_path
        ctx.transaction.metadata["health_status"] = health_status

        logger.info(
            "Computed health report for %s (%s)",
            Path(repo_path).name,
            health_status,
        )

        # Raise BusinessException for degraded or unhealthy reports
        # Health data is already persisted in ctx.state before the raise,
        # so stop=True has minimal downstream impact (WriteRepoReport is last skill).
        if health_status in ("degraded", "unhealthy"):
            raise BusinessException(
                f"Repo {Path(repo_path).name} is {health_status}",
                action=self.name,
                stop=True,
            )
