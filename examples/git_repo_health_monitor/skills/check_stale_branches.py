from __future__ import annotations

import subprocess
from datetime import datetime, timezone, timedelta

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)

class CheckStaleBranches(Skill):
    """Detect branches with no activity for more than configured days.

    Uses `git for-each-ref` to list branches with their last commit dates
    in a single subprocess call (avoids N+1 pattern). Branches older than the
    configured threshold are flagged.

    Stores ctx.data["stale_branches"] = list of branch name strings.
    Stores ctx.data["all_branches"] = list of all branch name strings.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_path = ctx.data.get("current_repo")
        if repo_path is None:
            raise SystemException(
                "No current_repo in context — main.py must set it first",
                action=self.name,
            )

        # Read stale branch threshold from config
        stale_branch_days = int(ctx.config["stale_branch_days"])

        # Get list of all branches (local + remote)
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "branch", "-a"],
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
                f"git branch timed out after 30s: {exc}",
                action=self.name,
            ) from exc
        except subprocess.SubprocessError as exc:
            raise SystemException(
                f"git branch failed: {exc}",
                action=self.name,
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise SystemException(
                f"git branch returned exit code {result.returncode}: {stderr}",
                action=self.name,
            )

        # Parse branch names (strip leading "* " for current branch)
        all_branches = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            branch = line.strip()
            # Skip detached HEAD — not a real branch
            if branch.startswith("(HEAD detached"):
                continue
            # Remove the current-branch marker
            if branch.startswith("* "):
                branch = branch[2:]
            # Skip remote-tracking branches for stale check (they are informational)
            if branch.startswith("remotes/"):
                continue
            all_branches.append(branch)

        # Use git for-each-ref to get all branches with their last commit dates in one call
        stale_branches = []
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=stale_branch_days)

        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "for-each-ref",
                 "--format=%(committerdate:iso) %(refname:short)", "refs/heads/"],
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
                f"git for-each-ref timed out after 30s: {exc}",
                action=self.name,
            ) from exc
        except subprocess.SubprocessError as exc:
            raise SystemException(
                f"git for-each-ref failed: {exc}",
                action=self.name,
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise SystemException(
                f"git for-each-ref returned exit code {result.returncode}: {stderr}",
                action=self.name,
            )

        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commit_date_str, branch = parts
                try:
                    commit_date = datetime.fromisoformat(commit_date_str).astimezone(timezone.utc)
                    if commit_date < cutoff:
                        stale_branches.append(branch.strip())
                except ValueError:
                    continue

        ctx.data["stale_branches"] = stale_branches
        ctx.data["all_branches"] = all_branches
        logger.info(
            "Found %d stale branches out of %d total in %s",
            len(stale_branches),
            len(all_branches),
            repo_path,
        )
