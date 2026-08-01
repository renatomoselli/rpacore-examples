from __future__ import annotations

import sys
from pathlib import Path

from rpacore import (
    ConfigField,
    Engine,
    ProcessContext,
    Status,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    save_transaction,
    validate_config,
)

from skills.row import FillRow, SubmitRow
from skills.score import RecordScore
from skills.setup import DownloadInputData, OpenChallengePage, StartChallenge
from skills._utils import find_row_value

logger = get_logger(__name__)
SETUP_DEFINITION_IDENTITY = "rpa-challenge/setup/v1"
ROW_DEFINITION_IDENTITY = "rpa-challenge/row/v1"
SCORE_DEFINITION_IDENTITY = "rpa-challenge/score/v1"
PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, allow_empty=False),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("screenshot_dir", str, required=False),
    ConfigField("xlsx_url", str, required=False, allow_empty=False),
    ConfigField("xlsx_allowed_hosts", (str, list), required=False),
    ConfigField("max_page_load_retries", int, required=False, min_value=1),
    ConfigField("headless", bool, required=False),
    ConfigField("timeout_page_load", int, required=False, min_value=1),
    ConfigField("timeout_click", int, required=False, min_value=1),
    ConfigField("timeout_form_transition", int, required=False, min_value=1),
    ConfigField("timeout_congratulations_check", int, required=False, min_value=1),
    ConfigField("timeout_score_extraction", int, required=False, min_value=1),
)
_CONFIG_PATH_KEYS = ("transaction_db_path", "screenshot_dir")


def _validate_config(config: dict[str, object]) -> dict[str, object]:
    """Validate public scalars, including whitespace-only strings, and retain domain rules."""
    try:
        validated = validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc

    for key in ("log_level", "transaction_db_path", "xlsx_url"):
        value = validated.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise SystemException(f"Config key '{key}' must be a non-empty string", action="main")

    allowed_hosts = validated.get("xlsx_allowed_hosts")
    if allowed_hosts is not None:
        valid_allowed_hosts = isinstance(allowed_hosts, str) or (
            isinstance(allowed_hosts, list) and all(isinstance(host, str) for host in allowed_hosts)
        )
        if not valid_allowed_hosts:
            raise SystemException(
                "Config key 'xlsx_allowed_hosts' must be a string or list of strings",
                action="main",
            )
    return validated


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


def _load_example_config() -> dict[str, object]:
    config = _validate_config(load_config(PROJECT_ROOT / "config.toml", require_file=True))
    path_keys = [
        key
        for key in _CONFIG_PATH_KEYS
        if key == "transaction_db_path" or config.get(key)
    ]
    return resolve_config_paths(
        config,
        path_keys,
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )


def main() -> None:
    config = _load_example_config()
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
            definition_identity=SETUP_DEFINITION_IDENTITY,
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
                definition_identity=ROW_DEFINITION_IDENTITY,
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
            definition_identity=SCORE_DEFINITION_IDENTITY,
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
