from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from uuid import uuid4

from rpacore import (
    BusinessException,
    ConfigField,
    Engine,
    ProcessContext,
    Status,
    Transaction,
    SystemException,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    save_transaction,
    validate_config,
)

from steps.check_working_tree import CheckWorkingTree
from steps.capture_recent_commits import CaptureRecentCommits
from steps.check_remotes import CheckRemotes
from steps.check_stale_branches import CheckStaleBranches
from steps.write_repo_report import WriteRepoReport
from steps.write_summary import WriteSummary
from create_sample_repos import prepare_sample_repos

logger = get_logger(__name__)
REPOSITORY_DEFINITION_IDENTITY = "git-repo-health-monitor/repository/v1"
SUMMARY_DEFINITION_IDENTITY = "git-repo-health-monitor/summary/v1"

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
DEFAULT_SAMPLE_REPOS = ["sample_repos/alpha", "sample_repos/beta"]
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, allow_empty=False),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("repos", list, allow_empty=False),
    ConfigField("output_file", str, allow_empty=False),
    ConfigField("stale_branch_days", int, min_value=1),
)
_CONFIG_PATH_KEYS = ("output_file", "transaction_db_path")


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
    failed_steps = repo_tx.failed_steps()
    failed_step = failed_steps[-1] if failed_steps else None
    exception = failed_step.exceptions[-1] if failed_step and failed_step.exceptions else None
    return {
        "repository": repo_path,
        "repo_name": Path(repo_path).name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_status": "failed",
        "failure_type": _exception_kind(exception),
        "classification": "technical_failure",
        "failed_step": failed_step.name if failed_step else "",
        "error": str(exception) if exception is not None else str(repo_tx.status),
        "uncommitted_changes": len(repo_tx.state.get("uncommitted_changes", [])),
        "recent_commits": repo_tx.state.get("recent_commits", []),
        "remotes": repo_tx.state.get("remotes", {}),
        "stale_branches": repo_tx.state.get("stale_branches", []),
        "branches": repo_tx.state.get("all_branches", []),
        "last_commit": None,
    }

def _validate_config(
    config: dict[str, object], *, allow_missing_repos: bool = False
) -> dict[str, object]:
    """Validate config without mutating caller input and resolve owned paths."""
    if "db_path" in config:
        raise SystemException(
            "Config key 'db_path' is unsupported; use 'transaction_db_path'.",
            action="main",
        )
    try:
        validated = validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc

    log_level = validated["log_level"]
    transaction_db_path = validated["transaction_db_path"]
    output_file = validated["output_file"]
    repos = validated["repos"]
    if (
        not isinstance(log_level, str)
        or not log_level.strip()
        or not isinstance(transaction_db_path, str)
        or not transaction_db_path.strip()
        or not isinstance(output_file, str)
        or not output_file.strip()
        or not isinstance(repos, list)
    ):
        raise SystemException("Invalid config field type", action="main")

    normalized_log_level = log_level.upper()
    if normalized_log_level not in LOG_LEVELS:
        raise SystemException(
            f"Config key 'log_level' must be one of {sorted(LOG_LEVELS)}, got {log_level!r}",
            action="main",
        )
    validated["log_level"] = normalized_log_level
    resolved_repos = []
    for repo_path in repos:
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

    resolved_config = dict(validated)
    resolved_config["repos"] = resolved_repos
    return resolve_config_paths(
        resolved_config,
        _CONFIG_PATH_KEYS,
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )


def _load_example_config() -> tuple[dict[str, object], bool]:
    config = load_config(PROJECT_ROOT / "config.toml", require_file=True)
    uses_default_sample_repos = _uses_default_sample_repos(config)
    return (
        _validate_config(config, allow_missing_repos=uses_default_sample_repos),
        uses_default_sample_repos,
    )


def main() -> None:
    config, uses_default_sample_repos = _load_example_config()
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
            definition_identity=REPOSITORY_DEFINITION_IDENTITY,
            state={
                "current_repo": repo_path,
                "output_file": output_file,
            },
            metadata={
                "example": "git_repo_health_monitor",
                "run_id": run_id,
            },
            steps=[
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
                health["failed_step"],
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
            failed_steps = repo_tx.failed_steps()
            if failed_steps:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed_steps)
                logger.warning("Repo %s failed: %s", Path(repo_path).name, details)
            else:
                logger.warning("Repo %s: %s", Path(repo_path).name, repo_tx.status)

    # --- Summary transaction ---
    summary_tx = Transaction(
        reference="summary-report",
        definition_identity=SUMMARY_DEFINITION_IDENTITY,
        state={
            "repo_health_records": repo_health_records,
            "output_file": output_file,
        },
        metadata={
            "example": "git_repo_health_monitor",
            "run_id": run_id,
        },
        steps=[
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
