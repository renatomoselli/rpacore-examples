from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class CaptureRecentCommits(Skill):
    """Capture the 10 most recent commits via `git log --oneline -10`.

    Stores ctx.data["recent_commits"] = list of {commit_hash, subject, timestamp} dicts.
    Raises SystemException if git is not installed or the path is not a git repo.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_path = ctx.data.get("current_repo")
        if repo_path is None:
            raise SystemException(
                "No current_repo in context — main.py must set it first",
                action=self.name,
            )

        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "log", "--oneline", "-10",
                 "--format=%H%x00%s%x00%ci"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise SystemException(
                "git command not found — is git installed?",
                action=self.name,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SystemException(
                f"git log timed out after 30s: {exc}",
                action=self.name,
            ) from exc
        except subprocess.SubprocessError as exc:
            raise SystemException(
                f"git log failed: {exc}",
                action=self.name,
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise SystemException(
                f"git log returned exit code {result.returncode}: {stderr}",
                action=self.name,
            )

        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\x00")
            if len(parts) == 3:
                commit_hash, subject, commit_date = parts
                try:
                    ts = datetime.fromisoformat(commit_date).astimezone(timezone.utc).isoformat()
                except (ValueError, AttributeError):
                    logger.warning(
                        "Could not parse commit date %r for commit %s, setting to 'unknown'",
                        commit_date,
                        commit_hash,
                    )
                    ts = "unknown"
                commits.append({
                    "commit_hash": commit_hash,
                    "subject": subject,
                    "timestamp": ts,
                })

        ctx.data["recent_commits"] = commits
        logger.info(
            "Captured %d recent commits from %s",
            len(commits),
            repo_path,
        )
