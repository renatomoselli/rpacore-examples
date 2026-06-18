from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from rpacore import SystemException


OLD_COMMIT_DATE = "2023-01-15T12:00:00+00:00"


def _run_git(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise SystemException(
            "git command not found while preparing sample repositories",
            action="prepare_sample_repos",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemException(
            f"git {' '.join(args)} timed out while preparing sample repositories",
            action="prepare_sample_repos",
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        raise SystemException(
            f"git {' '.join(args)} failed while preparing sample repositories: {stderr}",
            action="prepare_sample_repos",
        ) from exc


def _commit(repo_dir: Path, message: str, *, commit_date: str | None = None) -> None:
    env = os.environ.copy()
    if commit_date is not None:
        env["GIT_AUTHOR_DATE"] = commit_date
        env["GIT_COMMITTER_DATE"] = commit_date
    _run_git(["add", "."], cwd=repo_dir, env=env)
    _run_git(["commit", "-m", message], cwd=repo_dir, env=env)


def _git_stdout(args: list[str], *, cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise SystemException(
            "git command not found while preparing sample repositories",
            action="prepare_sample_repos",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemException(
            f"git {' '.join(args)} timed out while preparing sample repositories",
            action="prepare_sample_repos",
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        raise SystemException(
            f"git {' '.join(args)} failed while preparing sample repositories: {stderr}",
            action="prepare_sample_repos",
        ) from exc
    return result.stdout


def prepare_sample_repos(base: Path) -> None:
    """Create deterministic local repositories for the public example run."""
    base = base.resolve()

    # Clean up existing sample repos to allow re-runs
    if base.exists():
        def _remove_readonly(func, path, excinfo):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(base, onerror=_remove_readonly)

    base.mkdir(exist_ok=True)

    # Create healthy repo (alpha)
    alpha_dir = base / "alpha"
    alpha_dir.mkdir(exist_ok=True)
    _run_git(["init"], cwd=alpha_dir)
    _run_git(["config", "user.email", "sample@example.com"], cwd=alpha_dir)
    _run_git(["config", "user.name", "RPA Core Example"], cwd=alpha_dir)
    (alpha_dir / "README.md").write_text("Hello World\n")
    _commit(alpha_dir, "Initial commit")
    _run_git(["remote", "add", "origin", "https://github.com/example/alpha.git"], cwd=alpha_dir)

    # Create degraded repo (beta)
    beta_dir = base / "beta"
    beta_dir.mkdir(exist_ok=True)
    _run_git(["init"], cwd=beta_dir)
    _run_git(["config", "user.email", "sample@example.com"], cwd=beta_dir)
    _run_git(["config", "user.name", "RPA Core Example"], cwd=beta_dir)
    (beta_dir / "README.md").write_text("Beta Project\n")
    _commit(beta_dir, "Initial commit")
    default_branch = _git_stdout(["branch", "--show-current"], cwd=beta_dir).strip()

    # Create a stale branch
    _run_git(["checkout", "-b", "feature-old"], cwd=beta_dir)
    (beta_dir / "old_feature.txt").write_text("Old feature\n")
    _commit(beta_dir, "Old feature work", commit_date=OLD_COMMIT_DATE)

    # Go back to the default branch
    _run_git(["checkout", default_branch], cwd=beta_dir)

    # Create uncommitted changes
    (beta_dir / "uncommitted.txt").write_text("Uncommitted\n")


def main() -> None:
    prepare_sample_repos(Path("sample_repos"))


if __name__ == "__main__":
    main()
