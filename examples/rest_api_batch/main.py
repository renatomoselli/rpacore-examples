from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from rpacore import (
    ConfigField,
    Engine,
    OutcomeCategory,
    ProcessContext,
    RetryDisposition,
    Status,
    Transaction,
    SystemException,
    configure_logger,
    get_logger,
    load_config,
    save_transaction,
    validate_config,
)
from rpacore import resolve_config_paths

from skills.fetch_posts import FetchPosts
from skills.fetch_user import FetchUser
from skills.validate_post import ValidatePost
from skills.enrich_record import EnrichRecord
from skills.write_output import WriteOutput
from skills import API_MODES

logger = get_logger(__name__)
FETCH_DEFINITION_IDENTITY = "rest-api-batch/fetch/v1"
POST_DEFINITION_IDENTITY = "rest-api-batch/post/v1"
PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, allow_empty=False),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("output_file", str, allow_empty=False),
    ConfigField("api_mode", str, allow_empty=False),
)


def _validate_config(config: dict[str, object]) -> None:
    """Validate external configuration without mutating it."""
    try:
        validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc
    for key in ("log_level", "transaction_db_path", "output_file", "api_mode"):
        if not str(config[key]).strip():
            raise SystemException(f"Config key '{key}' must be a non-empty string", action="main")
    if config["api_mode"] not in API_MODES:
        raise SystemException(
            f"Config key 'api_mode' must be one of {sorted(API_MODES)}, got {config['api_mode']!r}",
            action="main",
        )


def _load_example_config() -> dict[str, object]:
    config = load_config(PROJECT_ROOT / "config.toml", require_file=True)
    _validate_config(config)
    return resolve_config_paths(
        config,
        ("transaction_db_path", "output_file"),
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )


def main() -> None:
    config = _load_example_config()
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["transaction_db_path"])
    output_file = str(config["output_file"])
    output_path = Path(output_file)

    # --- setup transaction: fetch all posts ---
    setup_tx = Transaction(
        reference="fetch-posts",
        definition_identity=FETCH_DEFINITION_IDENTITY,
        state={},
        skills=[
            FetchPosts(name="fetch_posts", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config))
    _persist_transaction(setup_tx, db_path=db_path, description="setup transaction")

    if setup_tx.status is not Status.SUCCESSFUL:
        failed = setup_tx.failed_skills()
        if failed:
            details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
            logger.error("Setup failed (%s). Failed skill(s): %s", setup_tx.status, details)
        else:
            logger.error("Setup failed (%s). Aborting.", setup_tx.status)
        sys.exit(1)

    posts = setup_tx.state.get("posts", [])
    logger.info("Fetched %d posts.", len(posts))

    output_backup = _preserve_existing_output(output_path)
    try:
        # --- one transaction per post ---
        for post in posts:
            post_id = post.get("id", "unknown")
            post_tx = Transaction(
                reference=f"post-{post_id}",
                definition_identity=POST_DEFINITION_IDENTITY,
                state={"current_post": post},
                skills=[
                    ValidatePost(name="validate_post", execution_order=1),
                    FetchUser(name="fetch_user", execution_order=2),
                    EnrichRecord(name="enrich_record", execution_order=3),
                    WriteOutput(name="write_output", execution_order=4),
                ],
            )
            engine.run(ProcessContext(transaction=post_tx, config=config))
            _persist_transaction(
                post_tx,
                db_path=db_path,
                description=f"transaction for post {post_id}",
            )

            if _post_requires_batch_rollback(post_tx):
                raise SystemException(
                    f"Post {post_id} exhausted retries; previous output will be restored",
                    action="main",
                )

            if post_tx.status == Status.SUCCESSFUL:
                logger.info(
                    "Post %s: %s...",
                    post_id,
                    post.get("title", "")[:50],
                )
            else:
                failed = post_tx.failed_skills()
                if failed:
                    details = "; ".join(
                        f"{s.name}({s.__class__.__name__})" for s in failed
                    )
                    logger.warning("Post %s failed: %s", post_id, details)
                else:
                    logger.warning("Post %s: %s", post_id, post_tx.status)
    except Exception:
        logger.warning(
            "Batch aborted; restoring the previous JSONL output. "
            "SQLite retains this run's attempted transactions as audit history."
        )
        _restore_previous_output(output_path, output_backup)
        raise
    else:
        _discard_output_backup(output_backup)

    if output_path.exists():
        logger.info("Batch complete. Output written to %s", output_file)
    else:
        logger.info("Batch complete. No output file was written; output target: %s", output_file)


def _persist_transaction(
    transaction: Transaction,
    *,
    db_path: str,
    description: str,
) -> None:
    """Persist a transaction or fail the batch when its audit record cannot be saved."""
    try:
        save_transaction(transaction, db_path=db_path)
    except (OSError, sqlite3.Error) as exc:
        raise SystemException(
            f"Could not persist {description}: {exc}",
            action="main",
        ) from exc


def _post_requires_batch_rollback(transaction: Transaction) -> bool:
    """Return the canonical terminal rollback decision for one post transaction."""
    outcome = (transaction.outcome_category, transaction.retry_disposition)
    if outcome == (OutcomeCategory.SUCCESSFUL, RetryDisposition.NOT_APPLICABLE):
        return False
    if outcome == (OutcomeCategory.BUSINESS_FAILED, RetryDisposition.NOT_REQUESTED):
        return False
    if outcome == (OutcomeCategory.SYSTEM_FAILED, RetryDisposition.RETRY_EXHAUSTED):
        return True
    raise SystemException(
        f"Post {transaction.reference} ended with unsupported outcome {outcome[0]}/{outcome[1]}",
        action="main",
    )


def _preserve_existing_output(output_path: Path) -> Path | None:
    """Move the previous run's output aside until the new batch succeeds."""
    if not output_path.exists():
        return None

    fd, backup_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".backup",
    )
    os.close(fd)
    backup_path = Path(backup_name)
    try:
        os.replace(output_path, backup_path)
    except OSError as exc:
        backup_path.unlink(missing_ok=True)
        raise SystemException(
            f"Could not preserve existing output file {output_path}: {exc}",
            action="main",
        ) from exc
    return backup_path


def _restore_previous_output(output_path: Path, backup_path: Path | None) -> None:
    """Remove partial output and restore the previous successful run."""
    try:
        if backup_path is None:
            output_path.unlink(missing_ok=True)
        else:
            os.replace(backup_path, output_path)
    except OSError as exc:
        raise SystemException(
            f"Could not restore previous output file {output_path}: {exc}",
            action="main",
        ) from exc


def _discard_output_backup(backup_path: Path | None) -> None:
    if backup_path is None:
        return
    try:
        backup_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove output backup %s: %s", backup_path, exc)


if __name__ == "__main__":
    main()
