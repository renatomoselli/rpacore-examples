from __future__ import annotations

import sys
from pathlib import Path

from rpacore import (
    Engine,
    ProcessContext,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    load_config,
    save_transaction,
)

from skills.row import FillRow, SubmitRow
from skills.score import RecordScore
from skills.setup import DownloadInputData, OpenChallengePage, StartChallenge


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )

    if config["max_retries"] < 0:
        raise SystemException("max_retries must be non-negative", action="main")


def _stop_playwright(shared_data: dict) -> None:
    pw = shared_data.pop("_pw", None)
    if pw is None:
        return
    try:
        pw.stop()
    except Exception:
        pass


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    screenshot_dir = str(config.get("screenshot_dir", ""))
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)

    engine = Engine(
        max_retries=int(config["max_retries"]),
        screenshot_dir=screenshot_dir,
    )
    db_path = str(config["db_path"])
    shared_data: dict = {}

    try:
        setup_tx = Transaction(
            reference="rpa-challenge-setup",
            skills=[
                OpenChallengePage(name="open_challenge_page", execution_order=1),
                DownloadInputData(name="download_input_data", execution_order=2),
                StartChallenge(name="start_challenge", execution_order=3),
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

        print(f"Configuration: max_retries={config['max_retries']}, db_path={db_path}")

        # The website keeps progress only inside the active browser session.
        # Persisted row transactions are useful for traceability, but a fresh
        # run must submit every row to reach the final score page.
        for row_index, row in enumerate(shared_data["rows"], start=1):
            email = str(row.get("Email", "")).strip() or f"row-{row_index}"
            ref = f"rpa-row-{email}"

            row_tx = Transaction(
                reference=ref,
                skills=[
                    FillRow(name="fill_row", execution_order=1, arguments={"row": row}),
                    SubmitRow(name="submit_row", execution_order=2),
                ],
            )
            engine.run(ProcessContext(transaction=row_tx, config=config, data=shared_data))
            save_transaction(row_tx, db_path=db_path)

        score_tx = Transaction(
            reference="rpa-challenge-score",
            skills=[
                RecordScore(name="record_score", execution_order=1),
            ],
        )
        engine.run(ProcessContext(transaction=score_tx, config=config, data=shared_data))
        save_transaction(score_tx, db_path=db_path)

        print(f"Final score: {shared_data.get('score', 'unknown')}")
    finally:
        _stop_playwright(shared_data)


if __name__ == "__main__":
    main()
