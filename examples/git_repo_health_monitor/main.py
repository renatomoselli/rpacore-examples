from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from uuid import uuid4

from rpacore import (
    BusinessException,
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
from rpacore import resolve_config_paths

from skills.check_working_tree import CheckWorkingTree
from skills.capture_recent_commits import CaptureRecentCommits
from skills.check_remotes import CheckRemotes
from skills.check_stale_branches import CheckStaleBranches
from skills.write_repo_report import WriteRepoReport
from skills.write_summary import WriteSummary
from create_sample_repos import prepare_sample_repos

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
DEFAULT_SAMPLE_REPOS = ["sample_repos/alpha", "sample_repos/beta"]


def _uses_default_sample_repos(config: dict) -> bool:
    return config.get("repos") == DEFAULT_SAMPLE_REPOS


def _resolve_repo_path(repo_path: str) -> str:
    path = Path(repo_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


def _exception_kind(exc: BaseException | None) -> str:
    if isinstance(exc, BusinessException):
        return "business"
    if isinstance(exc, SystemException):
        return "system"
    return "none"


def _failed_repo_record(repo_path: str, repo_tx: Transaction) -> dict[str, object]:
    failed_skills = repo_tx.failed_skills()
    failed_skill = failed_skills[-1] if failed_skills else None
    exception = failed_skill.exceptions[-1] if failed_skill and failed_skill.exceptions else None
    return {
        "repository": repo_path,
        "repo_name": Path(repo_path).name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_status": "failed",
        "failure_type": _exception_kind(exception),
        "classification": "technical_failure",
        "failed_skill": failed_skill.name if failed_skill else "",
        "error": str(exception) if exception is not None else str(repo_tx.status),
        "uncommitted_changes": len(repo_tx.state.get("uncommitted_changes", [])),
        "recent_commits": repo_tx.state.get("recent_commits", []),
        "remotes": repo_tx.state.get("remotes", {}),
        "stale_branches": repo_tx.state.get("stale_branches", []),
        "branches": repo_tx.state.get("all_branches", []),
        "last_commit": None,
    }

def _validate_config(config: dict, *, allow_missing_repos: bool = False) -> dict:
    """Validate config and resolve path values to absolute paths under PROJECT_ROOT."""
    if "transaction_db_path" not in config and "db_path" in config:
        logger.warning("Config key 'db_path' is deprecated; using it as 'transaction_db_path'.")
        config["transaction_db_path"] = config.pop("db_path")

    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
        ("repos", list),
        ("output_file", str),
        ("stale_branch_days", int),
    ):
        if key not in config:
            raise SystemException(
                f"Missing required config key: {key}", action="main",
            )
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, "
                f"got {type(config[key]).__name__}",
                action="main",
            )

    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )
    if config["stale_branch_days"] <= 0:
        raise SystemException(
            f"Config key 'stale_branch_days' must be > 0, got {config['stale_branch_days']}",
            action="main",
        )
    if config["log_level"].upper() not in LOG_LEVELS:
        raise SystemException(
            f"Config key 'log_level' must be one of {sorted(LOG_LEVELS)}, "
            f"got {config['log_level']!r}",
            action="main",
        )
    if not config["repos"]:
        raise SystemException(
            "Config key 'repos' must be a non-empty list",
            action="main",
        )
    resolved_repos = []
    for repo_path in config["repos"]:
        if not isinstance(repo_path, str) or not repo_path.strip():
            raise SystemException(
                f"Config key 'repos' contains empty or invalid path: {repo_path!r}",
                action="main",
            )
        resolved_repo_path = _resolve_repo_path(repo_path)
        if not allow_missing_repos and not Path(resolved_repo_path).is_dir():
            raise SystemException(
                f"Config key 'repos' path does not exist or is not a directory: {repo_path!r}",
                action="main",
            )
        resolved_repos.append(resolved_repo_path)

    config = resolve_config_paths(
        config,
        ["output_file", "transaction_db_path"],
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )
    config["repos"] = resolved_repos
    return config

def main() -> None:
    config = load_config("config.toml")
    uses_default_sample_repos = _uses_default_sample_repos(config)
    config = _validate_config(config, allow_missing_repos=uses_default_sample_repos)
    if uses_default_sample_repos:
        prepare_sample_repos(PROJECT_ROOT / "sample_repos")
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = config["transaction_db_path"]  # already resolved absolute by _validate_config
    output_file = config["output_file"]
    repos = config["repos"]
    run_id = str(uuid4())[:8]

    # Cross-repo accumulator (lives in main() scope, not in Transaction.state)
    repo_health_records: list[dict] = []

    # --- One transaction per repo ---
    successful = 0
    failed = 0
    persisted = 0
    persistence_failures: list[str] = []

    for repo_path in repos:
        repo_tx = Transaction(
            reference=f"repo-{Path(repo_path).name}",
            state={
                "current_repo": repo_path,
                "output_file": output_file,
            },
            metadata={
                "example": "git_repo_health_monitor",
                "run_id": run_id,
            },
            skills=[
                CheckWorkingTree(name="check_working_tree", execution_order=1),
                CaptureRecentCommits(name="capture_recent_commits", execution_order=2),
                CheckRemotes(name="check_remotes", execution_order=3),
                CheckStaleBranches(name="check_stale_branches", execution_order=4),
                WriteRepoReport(name="write_repo_report", execution_order=5),
            ],
        )
        engine.run(ProcessContext(transaction=repo_tx, config=config))

        if "health_report" in repo_tx.state:
            health = repo_tx.state["health_report"]
            repo_health_records.append(health)
            logger.info("Repo %s: %s", Path(repo_path).name, health.get("health_status", "unknown"))
        else:
            health = _failed_repo_record(repo_path, repo_tx)
            repo_health_records.append(health)
            logger.warning(
                "Repo %s: %s in %s",
                Path(repo_path).name,
                health["health_status"],
                health["failed_skill"],
            )

        try:
            save_transaction(repo_tx, db_path=db_path)
            persisted += 1
            health["persistence_status"] = "saved"
        except (OSError, sqlite3.Error) as exc:
            persistence_failures.append(repo_path)
            health["persistence_status"] = "failed"
            health["persistence_error"] = str(exc)
            logger.warning(
                "Could not persist transaction for %s: %s",
                repo_path,
                exc,
            )

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

    # --- Summary transaction ---
    summary_tx = Transaction(
        reference="summary-report",
        state={
            "repo_health_records": repo_health_records,
            "output_file": output_file,
        },
        metadata={
            "example": "git_repo_health_monitor",
            "run_id": run_id,
        },
        skills=[
            WriteSummary(name="write_summary", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=summary_tx, config=config))
    try:
        save_transaction(summary_tx, db_path=db_path)
        persisted += 1
    except (OSError, sqlite3.Error) as exc:
        logger.warning(
            "Could not persist summary transaction: %s",
            exc,
        )

    logger.info(
        "Health check complete. %d successful, %d failed out of %d repos. "
        "Persisted %d/%d transactions. Output: %s",
        successful, failed, len(repos), persisted, len(repos) + 1, output_file,
    )
    if persistence_failures:
        logger.warning(
            "Transactions not persisted for repos: %s",
            ", ".join(persistence_failures),
        )

if __name__ == "__main__":
    main()
