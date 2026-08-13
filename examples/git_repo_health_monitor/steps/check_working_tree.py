from __future__ import annotations

import subprocess

from rpacore import ProcessContext, Step, SystemException, get_logger

logger = get_logger(__name__)


class CheckWorkingTree(Step):
    """Check for uncommitted changes in the working tree via `git status --porcelain`.

    Stores ctx.state["uncommitted_changes"] = list of changed file paths.
    Raises SystemException if git is not installed or the path is not a git repo.
    """

    def execute(self, ctx: ProcessContext) -> None:
        repo_path = ctx.require_state("current_repo", str, action=self.name)

        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise SystemException(
                "git command not found \u2014 is git installed?",
                action=self.name,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SystemException(
                f"git status timed out after 30s: {exc}",
                action=self.name,
            ) from exc
        except OSError as exc:
            raise SystemException(
                f"git status failed: {exc}",
                action=self.name,
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise SystemException(
                f"git status returned exit code {result.returncode}: {stderr}",
                action=self.name,
            )

        # Parse porcelain output: each line is "XY filename"
        changed_files = []
        for line in result.stdout.splitlines():
            if line:
                # Format: "XY filename" where X=status_index, Y=status_working_tree
                filename = line[3:]
                if line[:2].strip().startswith(("R", "C")) and " -> " in filename:
                    filename = filename.split(" -> ", 1)[1]
                changed_files.append(filename)

        ctx.state["uncommitted_changes"] = changed_files
        logger.info(
            "Found %d uncommitted changes in %s",
            len(changed_files),
            repo_path,
        )
