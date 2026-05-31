from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def main() -> None:
    base = Path("sample_repos")

    # Clean up existing sample repos to allow re-runs
    if base.exists():
        import shutil

        def _remove_readonly(func, path, excinfo):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(base, onexc=_remove_readonly)

    base.mkdir(exist_ok=True)

    # Configure git identity
    for cmd in [
        ["git", "config", "user.email", "test@test.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, check=True, timeout=10)

    # Create healthy repo (alpha)
    alpha_dir = base / "alpha"
    alpha_dir.mkdir(exist_ok=True)
    subprocess.run(["git", "-C", str(alpha_dir), "init"], check=True, timeout=10)
    (alpha_dir / "README.md").write_text("Hello World\n")
    subprocess.run(
        ["git", "-C", str(alpha_dir), "add", "README.md"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(alpha_dir), "commit", "-m", "Initial commit"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(alpha_dir), "remote", "add", "origin", "https://github.com/example/alpha.git"],
        check=True, timeout=10,
    )

    # Create degraded repo (beta)
    beta_dir = base / "beta"
    beta_dir.mkdir(exist_ok=True)
    subprocess.run(["git", "-C", str(beta_dir), "init"], check=True, timeout=10)
    (beta_dir / "README.md").write_text("Beta Project\n")
    subprocess.run(
        ["git", "-C", str(beta_dir), "add", "README.md"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(beta_dir), "commit", "-m", "Initial commit"],
        check=True, timeout=10,
    )

    # Create a stale branch
    subprocess.run(
        ["git", "-C", str(beta_dir), "checkout", "-b", "feature-old"],
        check=True, timeout=10,
    )
    (beta_dir / "old_feature.txt").write_text("Old feature\n")
    subprocess.run(
        ["git", "-C", str(beta_dir), "add", "old_feature.txt"],
        check=True, timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(beta_dir), "commit", "-m", "Old feature work"],
        check=True, timeout=10,
    )

    # Go back to main
    subprocess.run(
        ["git", "-C", str(beta_dir), "checkout", "-"],
        check=True, timeout=10,
    )

    # Create uncommitted changes
    (beta_dir / "uncommitted.txt").write_text("Uncommitted\n")


if __name__ == "__main__":
    main()
