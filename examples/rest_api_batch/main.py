from __future__ import annotations

import sys

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

from skills import KEY_POSTS, KEY_CURRENT_POST, KEY_CURRENT_USER, KEY_ENRICHED_RECORD
from skills.fetch_posts import FetchPosts
from skills.fetch_user import FetchUser
from skills.validate_post import ValidatePost
from skills.enrich_record import EnrichRecord
from skills.write_output import WriteOutput

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("output_file", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    # Range validation (G2)
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["db_path"])
    output_file = str(config["output_file"])
    shared_data: dict = {}

    # --- setup transaction: fetch all posts ---
    setup_tx = Transaction(
        reference="fetch-posts",
        skills=[
            FetchPosts(name="fetch_posts", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config, data=shared_data))
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

    posts = shared_data.get(KEY_POSTS, [])
    logger.info("Fetched %d posts.", len(posts))

    # --- one transaction per post ---
    for post in posts:
        shared_data[KEY_CURRENT_POST] = post

        # Clear stale shared state from previous transaction
        shared_data.pop(KEY_CURRENT_USER, None)
        shared_data.pop(KEY_ENRICHED_RECORD, None)

        post_id = post.get("id", "unknown")
        post_tx = Transaction(
            reference=f"post-{post_id}",
            skills=[
                FetchUser(name="fetch_user", execution_order=1),
                ValidatePost(name="validate_post", execution_order=2),
                EnrichRecord(name="enrich_record", execution_order=3),
                WriteOutput(name="write_output", execution_order=4),
            ],
        )
        engine.run(ProcessContext(transaction=post_tx, config=config, data=shared_data))
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

    logger.info("Batch complete. Output written to %s", output_file)


if __name__ == "__main__":
    main()
