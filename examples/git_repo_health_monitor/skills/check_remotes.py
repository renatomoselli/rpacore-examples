from __future__ import annotations

import subprocess

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class CheckRemotes(Skill):
    """Check remote configuration via `git remote -v`.

    Stores ctx.data["remotes"] = dict mapping remote name → URL string.
    Raises SystemException if git is not installed or the path is not a git repo.
    No exception is raised for repos without remotes — WriteRepoReport will
    count "no remotes" as a health degradation.
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
                ["git", "-C", repo_path, "remote", "-v"],
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
                f"git remote timed out after 30s: {exc}",
                action=self.name,
            ) from exc
        except subprocess.SubprocessError as exc:
            raise SystemException(
                f"git remote failed: {exc}",
                action=self.name,
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise SystemException(
                f"git remote returned exit code {result.returncode}: {stderr}",
                action=self.name,
            )

        remotes = {}
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                remote_name = parts[0]
                remote_url = parts[1]
                # git remote -v outputs push/fetch URLs separately; keep first seen
                if remote_name not in remotes:
                    remotes[remote_name] = remote_url

        # No remotes is not an error — just an empty dict.
        # WriteRepoReport will count "no remotes" as a health degradation.
        ctx.data["remotes"] = remotes
        logger.info(
            "Found %d remotes in %s",
            len(remotes),
            repo_path,
        )
