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
from rpacore.paths import resolve_config_paths

from skills.fetch_posts import FetchPosts
from skills.fetch_user import FetchUser
from skills.validate_post import ValidatePost
from skills.enrich_record import EnrichRecord
from skills.write_output import WriteOutput
from skills import API_MODES

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
        ("output_file", str),
        ("api_mode", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    # Range validation
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )
    if config["api_mode"] not in API_MODES:
        raise SystemException(
            f"Config key 'api_mode' must be one of {sorted(API_MODES)}, got {config['api_mode']!r}",
            action="main",
        )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    config = resolve_config_paths(
        config,
        ["transaction_db_path", "output_file"],
        base_dir=PROJECT_ROOT,
    )
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=config["max_retries"])
    db_path = str(config["transaction_db_path"])
    output_file = str(config["output_file"])
    output_path = Path(output_file)

    # --- setup transaction: fetch all posts ---
    setup_tx = Transaction(
        reference="fetch-posts",
        state={},
        skills=[
            FetchPosts(name="fetch_posts", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config))
    try:
        save_transaction(setup_tx, db_path=db_path)
    except OSError as exc:
        logger.warning("Could not persist setup transaction: %s", exc)

    if setup_tx.status is not Status.SUCCESSFUL:
        failed = setup_tx.failed_skills()
        if failed:
            details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
            logger.error("Setup failed (%s). Failed skill(s): %s", setup_tx.status, details)
        else:
            logger.error("Setup failed (%s). Aborting.", setup_tx.status)
        sys.exit(1)

    if output_path.exists():
        output_path.unlink()

    posts = setup_tx.state.get("posts", [])
    logger.info("Fetched %d posts.", len(posts))

    # --- one transaction per post ---
    for post in posts:
        post_id = post.get("id", "unknown")
        post_tx = Transaction(
            reference=f"post-{post_id}",
            state={"current_post": post},
            skills=[
                ValidatePost(name="validate_post", execution_order=1),
                FetchUser(name="fetch_user", execution_order=2),
                EnrichRecord(name="enrich_record", execution_order=3),
                WriteOutput(name="write_output", execution_order=4),
            ],
        )
        engine.run(ProcessContext(transaction=post_tx, config=config))
        try:
            save_transaction(post_tx, db_path=db_path)
        except OSError as exc:
            logger.warning("Could not persist transaction for post %s: %s", post_id, exc)

        if post_tx.status == Status.SUCCESSFUL:
            logger.info(
                "Post %s: %s...",
                post_id,
                post.get("title", "")[:50],
            )
        else:
            failed = post_tx.failed_skills()
            if failed:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
                logger.warning("Post %s failed: %s", post_id, details)
            else:
                logger.warning("Post %s: %s", post_id, post_tx.status)

    if output_path.exists():
        logger.info("Batch complete. Output written to %s", output_file)
    else:
        logger.info("Batch complete. No output file was written; output target: %s", output_file)


if __name__ == "__main__":
    main()
