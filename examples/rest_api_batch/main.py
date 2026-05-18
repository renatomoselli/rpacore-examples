from __future__ import annotations

import sys
from pathlib import Path

from oref import (
    Engine,
    ProcessContext,
    Status,
    Transaction,
    SystemException,
    configure_logger,
    load_config,
    save_transaction,
)

from skills.fetch_posts import FetchPosts
from skills.fetch_user import FetchUser
from skills.validate_post import ValidatePost
from skills.enrich_record import EnrichRecord
from skills.write_output import WriteOutput


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
        ("output_file", str),
    ):
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
        if not isinstance(config[key], expected_type):
            raise ValueError(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}"
            )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["db_path"])
    shared_data: dict = {}

    # --- setup transaction: fetch all posts ---
    setup_tx = Transaction(
        reference="fetch-posts",
        skills=[
            FetchPosts(name="fetch_posts", execution_order=1),
        ],
    )
    engine.run(ProcessContext(transaction=setup_tx, config=config, data=shared_data))
    save_transaction(setup_tx, db_path=db_path)

    if setup_tx.status is not Status.SUCCESSFUL:
        failed = setup_tx.failed_skills()
        if failed:
            details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
            print(f"Setup failed ({setup_tx.status}). Failed skill(s): {details}")
        else:
            print(f"Setup failed ({setup_tx.status}). Aborting.")
        sys.exit(1)

    posts = shared_data.get("posts", [])
    print(f"Fetched {len(posts)} posts.")

    # --- one transaction per post ---
    for post in posts:
        shared_data["current_post"] = post

        post_tx = Transaction(
            reference=f"post-{post.get('id')}",
            skills=[
                FetchUser(name="fetch_user", execution_order=1),
                ValidatePost(name="validate_post", execution_order=2),
                EnrichRecord(name="enrich_record", execution_order=3),
                WriteOutput(name="write_output", execution_order=4),
            ],
        )
        engine.run(ProcessContext(transaction=post_tx, config=config, data=shared_data))
        save_transaction(post_tx, db_path=db_path)

        if post_tx.status == Status.SUCCESSFUL:
            print(f"  ✓ Post {post.get('id')}: {post.get('title', '')[:50]}...")
        else:
            failed = post_tx.failed_skills()
            if failed:
                details = "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)
                print(f"  ✗ Post {post.get('id')}: {details}")
            else:
                print(f"  ✗ Post {post.get('id')}: {post_tx.status}")

    print(f"Batch complete. Output written to {config.get('output_file', 'output.jsonl')}")


if __name__ == "__main__":
    main()
