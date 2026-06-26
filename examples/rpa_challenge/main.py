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
    get_logger,
    load_config,
    save_transaction,
)
from rpacore import resolve_config_paths

from skills.row import FillRow, SubmitRow
from skills.score import RecordScore
from skills.setup import DownloadInputData, OpenChallengePage, StartChallenge
from skills._utils import find_row_value

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if type(config[key]) is not expected_type:
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )

    if config["max_retries"] < 0:
        raise SystemException("max_retries must be non-negative", action="main")

    allowed_hosts = config.get("xlsx_allowed_hosts")
    if allowed_hosts is not None:
        valid_allowed_hosts = isinstance(allowed_hosts, str) or (
            isinstance(allowed_hosts, list) and all(isinstance(host, str) for host in allowed_hosts)
        )
        if not valid_allowed_hosts:
            raise SystemException(
                "Config key 'xlsx_allowed_hosts' must be a string or list of strings",
                action="main",
            )


def _format_failed_skills(tx: Transaction) -> str:
    failed = tx.failed_skills()
    if not failed:
        return "none"
    return "; ".join(f"{s.name}({s.__class__.__name__})" for s in failed)


def _display_path(path: str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _stop_playwright(shared_resources: dict) -> None:
    pw = shared_resources.pop("_pw", None)
    if pw is None:
        return
    try:
        pw.stop()
    except Exception:
        pass


def _browser_page_available(shared_resources: dict) -> bool:
    page = shared_resources.get("page")
    if page is None:
        return False
    is_closed = getattr(page, "is_closed", None)
    if not callable(is_closed):
        return False
    try:
        return not bool(is_closed())
    except Exception as exc:
        logger.warning("Could not verify browser page health: %s", exc)
        return False


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    path_keys = ["transaction_db_path"]
    if str(config.get("screenshot_dir", "")):
        path_keys.append("screenshot_dir")
    config = resolve_config_paths(
        config,
        path_keys,
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )
    configure_logger(level=str(config["log_level"]))

    screenshot_dir = str(config.get("screenshot_dir", ""))
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)

    engine = Engine(
        max_retries=int(config["max_retries"]),
        screenshot_dir=screenshot_dir,
    )
    row_engine = Engine(max_retries=0, screenshot_dir=screenshot_dir)
    transaction_db_path = str(config["transaction_db_path"])
    shared_resources: dict = {}

    try:
        setup_tx = Transaction(
            reference="rpa-challenge-setup",
            skills=[
                OpenChallengePage(name="open_challenge_page", execution_order=1),
                DownloadInputData(name="download_input_data", execution_order=2),
                StartChallenge(name="start_challenge", execution_order=3),
            ],
        )
        engine.run(ProcessContext(transaction=setup_tx, config=config, resources=shared_resources))
        try:
            save_transaction(setup_tx, db_path=transaction_db_path)
        except OSError as exc:
            logger.warning("Could not persist setup transaction: %s", exc)

        if setup_tx.status is not Status.SUCCESSFUL:
            details = _format_failed_skills(setup_tx)
            print(f"Setup failed ({setup_tx.status}). Failed skill(s): {details}")
            sys.exit(1)

        print(
            f"Configuration: max_retries={config['max_retries']}, "
            f"transaction_db_path={_display_path(transaction_db_path)}"
        )

        # Read durable rows from transaction state (persisted by DownloadInputData)
        rows = setup_tx.state.get("rows")
        if not rows:
            print("Setup completed but no rows were parsed. Check that the Excel download and parsing succeeded.")
            sys.exit(1)

        # The website keeps progress only inside the active browser session.
        # Persisted row transactions are useful for traceability, but a fresh
        # run must submit every row to reach the final score page. Row
        # transactions deliberately use no engine retries because SubmitRow is
        # non-idempotent: retrying a successful click can advance the challenge
        # with stale form data.
        for row_index, row in enumerate(rows, start=1):
            if not _browser_page_available(shared_resources):
                print(
                    "Browser session is not available before row "
                    f"{row_index}; restart the example to begin a fresh challenge session."
                )
                sys.exit(1)

            email = find_row_value(row, "Email").strip() or f"anonymous-{row_index}"
            ref = f"rpa-row-{row_index}-{email}"

            row_tx = Transaction(
                reference=ref,
                skills=[
                    FillRow(name="fill_row", execution_order=1, arguments={"row": row}),
                    SubmitRow(name="submit_row", execution_order=2),
                ],
            )
            row_engine.run(ProcessContext(transaction=row_tx, config=config, resources=shared_resources))
            try:
                save_transaction(row_tx, db_path=transaction_db_path)
            except OSError as exc:
                logger.warning("Could not persist row %s transaction: %s", row_index, exc)
            if row_tx.status is not Status.SUCCESSFUL:
                details = _format_failed_skills(row_tx)
                print(f"Row {row_index} failed ({row_tx.status}). Failed skill(s): {details}")
                sys.exit(1)

        score_tx = Transaction(
            reference="rpa-challenge-score",
            skills=[
                RecordScore(name="record_score", execution_order=1),
            ],
        )
        if not _browser_page_available(shared_resources):
            print("Browser session is not available before score capture; restart the example.")
            sys.exit(1)
        engine.run(ProcessContext(transaction=score_tx, config=config, resources=shared_resources))
        try:
            save_transaction(score_tx, db_path=transaction_db_path)
        except OSError as exc:
            logger.warning("Could not persist score transaction: %s", exc)
        if score_tx.status is not Status.SUCCESSFUL:
            details = _format_failed_skills(score_tx)
            print(f"Score capture failed ({score_tx.status}). Failed skill(s): {details}")
            sys.exit(1)
        score = score_tx.state.get("score")
        if not score:
            print("Score capture completed but no score was recorded.")
            sys.exit(1)

        print(f"Final score: {score}")
    finally:
        _stop_playwright(shared_resources)


if __name__ == "__main__":
    main()
