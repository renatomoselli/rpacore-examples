from __future__ import annotations

import sys
from pathlib import Path

from rpacore import (
    Engine,
    ProcessContext,
    Status,
    Transaction,
    SystemException,
    configure_logger,
    get_logger,
    load_config,
    save_transaction,
)

from skills.check_working_tree import CheckWorkingTree
from skills.capture_recent_commits import CaptureRecentCommits
from skills.check_remotes import CheckRemotes
from skills.check_stale_branches import CheckStaleBranches
from skills.write_repo_report import WriteRepoReport
from skills.write_summary import WriteSummary

logger = get_logger(__name__)

def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("repos", list),
        ("output_file", str),
        ("stale_branch_days", int),  # [Q1/I2]
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )
    if config["stale_branch_days"] <= 0:  # [Q1/I2] range check
        raise SystemException(
            f"Config key 'stale_branch_days' must be > 0, got {config['stale_branch_days']}",
            action="main",
        )
    if config["log_level"].upper() not in valid_levels:
        raise SystemException(
            f"Config key 'log_level' must be one of {valid_levels}, got {config['log_level']!r}",
            action="main",
        )
    if not config["repos"]:
        raise SystemException(
            "Config key 'repos' must be a non-empty list",
            action="main",
        )
    for repo_path in config["repos"]:
        if not isinstance(repo_path, str) or not repo_path.strip():
            raise SystemException(
                f"Config key 'repos' contains empty or invalid path: {repo_path!r}",
                action="main",
            )
        if not Path(repo_path).is_dir():
            raise SystemException(
                f"Config key 'repos' path does not exist on disk: {repo_path!r}",
                action="main",
            )

def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["db_path"])
    output_file = str(config["output_file"])
    repos = config["repos"]
    shared_data: dict = {}

    # Clear transaction DB for idempotent runs
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()

    if not repos:
        logger.warning("No repos configured in 'repos'. Exiting.")
        # Still produce an empty summary
        summary_tx = Transaction(
            reference="summary-report",
            skills=[WriteSummary(name="write_summary", execution_order=1)],
        )
        engine.run(ProcessContext(transaction=summary_tx, config=config, data=shared_data))
        save_transaction(summary_tx, db_path=db_path)
        return

    # --- One transaction per repo ---
    successful = 0
    failed = 0
    repo_health_records: list[dict] = []

    for repo_path in repos:
        # Clear all shared state from previous transaction
        shared_data.clear()

        shared_data["current_repo"] = repo_path
        shared_data["output_file"] = output_file

        repo_tx = Transaction(
            reference=f"repo-{Path(repo_path).name}",
            skills=[
                CheckWorkingTree(name="check_working_tree", execution_order=1),
                CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                CheckRemotes(name="check_remotes", execution_order=3),
                CheckStaleBranches(name="check_stale_branches", execution_order=4),
                WriteRepoReport(name="write_repo_report", execution_order=5),
            ],
        )
        engine.run(ProcessContext(transaction=repo_tx, config=config, data=shared_data))
        try:
            save_transaction(repo_tx, db_path=db_path)
        except OSError as exc:
            logger.warning("Could not persist transaction for %s: %s", repo_path, exc)

        if "health_report" in shared_data:  # [I8] explicit key-checking
            health = shared_data["health_report"]
            repo_health_records.append(health)
            logger.info("Repo %s: %s", Path(repo_path).name, health.get("health_status", "unknown"))

        if repo_tx.status == Status.SUCCESSFUL:
            successful += 1
        else:
            failed += 1
            failed_skills = repo_tx.failed_skills()
            if failed_skills:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed_skills)
                logger.warning("Repo %s failed: %s", Path(repo_path).name, details)
            else:
                logger.warning("Repo %s: %s", Path(repo_path).name, repo_tx.status)

    # --- Summary transaction with error handling [I9] ---
    summary_tx = Transaction(
        reference="summary-report",
        skills=[
            WriteSummary(name="write_summary", execution_order=1),
        ],
    )
    # Pass collected health data via shared_data
    shared_data["repo_health_records"] = repo_health_records
    try:
        engine.run(ProcessContext(transaction=summary_tx, config=config, data=shared_data))
        save_transaction(summary_tx, db_path=db_path)
    except Exception as exc:
        logger.error("Summary transaction failed: %s", exc)
        # Clean up partial summary file
        summary_path = Path(output_file).with_suffix(".summary.json")
        if summary_path.exists():
            summary_path.unlink()
        raise

    logger.info(
        "Health check complete. %d successful, %d failed out of %d repos. Output: %s",
        successful, failed, len(repos), output_file,
    )

if __name__ == "__main__":
    main()
