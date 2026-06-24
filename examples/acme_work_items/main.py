from __future__ import annotations

"""ACME Work Items — durable queue-driven browser automation capstone."""

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from uuid import uuid4

from rpacore import (
    BusinessException,
    CredentialProvider,
    Engine,
    ProcessContext,
    QueueItem,
    QueueRunSummary,
    Notifier,
    SqliteQueue,
    Status,
    SystemException,
    Transaction,
    build_credential_provider,
    build_notifiers,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    run_queue_loop,
    save_transaction,
)

from skills._session import BrowserSession, DiscoveredItem, validate_work_item_id
from skills.close_work_item import CloseWorkItem
from skills.compute_security_hash import ComputeSecurityHash
from skills.fetch_work_item import FetchWorkItem
from skills.update_work_item import UpdateWorkItem
from skills.validate_work_item import ValidateWorkItem
from skills.write_summary import WriteSummary


logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH_KEYS = (
    "transaction_db_path",
    "queue.db_path",
    "screenshot_dir",
    "report_dir",
)
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class RunResult:
    run_id: str
    enqueued: int
    queue_summary: QueueRunSummary
    summary_transaction: Transaction


def _expect_type(config: dict[str, object], key: str, expected: type) -> object:
    if key not in config:
        raise SystemException(f"Missing required config key: {key}", action="main")
    value = config[key]
    if type(value) is not expected:
        raise SystemException(
            f"Config key {key!r} must be {expected.__name__}, got {type(value).__name__}",
            action="main",
        )
    return value


def _validate_config(config: dict[str, object]) -> None:
    for key, expected in (
        ("max_retries", int),
        ("log_level", str),
        ("log_format", str),
        ("transaction_db_path", str),
        ("screenshot_dir", str),
        ("report_dir", str),
        ("report_max_records", int),
        ("base_url", str),
        ("credential_provider", str),
        ("headless", bool),
        ("page_load_timeout_ms", int),
        ("action_timeout_ms", int),
    ):
        _expect_type(config, key, expected)

    for key in ("retry_delay", "retry_backoff"):
        if key not in config or isinstance(config[key], bool) or not isinstance(config[key], (int, float)):
            raise SystemException(f"Config key {key!r} must be a number", action="main")

    if int(config["max_retries"]) < 0:
        raise SystemException("max_retries must be >= 0", action="main")
    if float(config["retry_delay"]) < 0 or not math.isfinite(float(config["retry_delay"])):
        raise SystemException("retry_delay must be >= 0", action="main")
    if float(config["retry_backoff"]) < 1 or not math.isfinite(float(config["retry_backoff"])):
        raise SystemException("retry_backoff must be >= 1", action="main")
    for key in ("report_max_records", "page_load_timeout_ms", "action_timeout_ms"):
        if int(config[key]) <= 0:
            raise SystemException(f"{key} must be > 0", action="main")
    if str(config["log_level"]).upper() not in _LOG_LEVELS:
        raise SystemException("log_level is invalid", action="main")
    if config["log_format"] not in {"text", "json"}:
        raise SystemException("log_format must be 'text' or 'json'", action="main")
    if config["credential_provider"] not in {"env", "keyring"}:
        raise SystemException("credential_provider must be 'env' or 'keyring'", action="main")
    for key in ("transaction_db_path", "screenshot_dir", "report_dir"):
        if not str(config[key]).strip():
            raise SystemException(f"{key} must be a non-empty path", action="main")

    parsed = urlparse(str(config["base_url"]))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemException("base_url must be an absolute HTTP(S) URL", action="main")
    if parsed.username or parsed.password:
        raise SystemException("base_url must not contain embedded credentials", action="main")

    queue_config = config.get("queue")
    if not isinstance(queue_config, dict):
        raise SystemException("Missing required [queue] section", action="main")
    for key, expected in (("db_path", str), ("lease_timeout", int), ("max_retries", int)):
        if key not in queue_config or type(queue_config[key]) is not expected:
            raise SystemException(f"queue.{key} has an invalid type", action="main")
    if not queue_config["db_path"]:
        raise SystemException("queue.db_path must be non-empty", action="main")
    if queue_config["lease_timeout"] <= 0 or queue_config["max_retries"] < 0:
        raise SystemException("queue lease/retry values are out of range", action="main")


def _load_example_config(path: Path | None = None) -> dict[str, object]:
    config_path = path or PROJECT_ROOT / "config.toml"
    config = load_config(config_path, require_file=True)
    _validate_config(config)
    root = PROJECT_ROOT if config_path.resolve().is_relative_to(PROJECT_ROOT) else config_path.resolve().parent
    return resolve_config_paths(
        config,
        _CONFIG_PATH_KEYS,
        base_dir=config_path.resolve().parent,
        root=root,
    )


def _new_browser_session(config: dict[str, object]) -> BrowserSession:
    return BrowserSession(
        str(config["base_url"]),
        headless=bool(config["headless"]),
        page_load_timeout_ms=int(config["page_load_timeout_ms"]),
        action_timeout_ms=int(config["action_timeout_ms"]),
    )


def _validated_discovery(item: DiscoveredItem) -> DiscoveredItem:
    try:
        validate_work_item_id(item.work_item_id)
    except ValueError as exc:
        raise SystemException("Discovered work item has an invalid identifier", action="scan_inbox") from exc
    if not isinstance(item.discovered_hash, str) or not item.discovered_hash:
        raise SystemException("Discovered work item has no concurrency fingerprint", action="scan_inbox")
    return item


def scan_inbox(
    config: dict[str, object],
    queue: SqliteQueue,
    credentials: CredentialProvider,
    *,
    session_factory: Callable[[dict[str, object]], BrowserSession] = _new_browser_session,
) -> int:
    """Discover remote open items in a short-lived session and seed the queue."""
    session = session_factory(config)
    with session:
        session.ensure_authenticated(credentials)
        discovered = session.discover_open_items()

    added = 0
    seen: set[str] = set()
    for raw in discovered:
        item = _validated_discovery(raw)
        if item.work_item_id in seen:
            continue
        seen.add(item.work_item_id)
        if queue.add_once(
            QueueItem(
                reference=f"acme-{item.work_item_id}",
                payload={
                    "work_item_id": item.work_item_id,
                    "discovered_hash": item.discovered_hash,
                },
            )
        ):
            added += 1
    return added


def build_transaction(item: QueueItem, *, run_id: str = "manual") -> Transaction:
    if set(item.payload) != {"work_item_id", "discovered_hash"}:
        raise SystemException("Queue payload must contain exactly work_item_id and discovered_hash", action="build_transaction")
    work_item_id = item.payload.get("work_item_id")
    discovered_hash = item.payload.get("discovered_hash")
    if not isinstance(work_item_id, str) or not isinstance(discovered_hash, str) or not discovered_hash:
        raise SystemException("Queue payload contains invalid values", action="build_transaction")
    try:
        validate_work_item_id(work_item_id)
    except ValueError as exc:
        raise SystemException("Queue payload contains an invalid work_item_id", action="build_transaction") from exc
    return Transaction(
        reference=item.reference,
        metadata={"example": "acme_work_items", "work_item_id": work_item_id, "run_id": run_id},
        skills=[
            FetchWorkItem(name="fetch_work_item", execution_order=1),
            ValidateWorkItem(name="validate_work_item", execution_order=2),
            ComputeSecurityHash(name="compute_security_hash", execution_order=3),
            UpdateWorkItem(name="update_work_item", execution_order=4),
            CloseWorkItem(name="close_work_item", execution_order=5),
        ],
    )


def _failure_details(transaction: Transaction | None, error: Exception | None) -> tuple[str, str, str]:
    failed_skill = ""
    exception: BaseException | None = error
    if transaction is not None:
        failed = transaction.failed_skills()
        if failed:
            failed_skill = failed[-1].name
            if failed[-1].exceptions:
                exception = failed[-1].exceptions[-1]
    if isinstance(exception, BusinessException):
        return failed_skill, "business", str(exception)[:300]
    if isinstance(exception, SystemException):
        return failed_skill, "system", str(exception)[:300]
    if exception is not None:
        return failed_skill, "unexpected", "Unexpected item-processing error"
    return failed_skill, "none", ""


def _project_outcome(
    item: QueueItem,
    transaction: Transaction | None,
    error: Exception | None,
) -> dict[str, object]:
    failed_skill, classification, message = _failure_details(transaction, error)
    return {
        "work_item_id": item.payload.get("work_item_id", ""),
        "queue_reference": item.reference,
        "transaction_id": transaction.id if transaction else "",
        "status": str(transaction.status) if transaction else "failed",
        "retry_count": transaction.retry_count if transaction else item.retry_count,
        "failed_skill": failed_skill,
        "classification": classification,
        "message": message,
        "idempotency_outcome": transaction.state.get("idempotency_outcome", "") if transaction else "",
        "artifact_paths": [artifact.path for artifact in transaction.artifacts] if transaction else [],
    }


def _queue_summary_state(summary: QueueRunSummary) -> dict[str, int]:
    return {key: int(value) for key, value in asdict(summary).items()}


def _run_summary_transaction(
    config: dict[str, object],
    engine: Engine,
    *,
    run_id: str,
    records: list[dict[str, object]],
    omitted_record_count: int,
    queue_summary: QueueRunSummary,
    credentials: CredentialProvider,
) -> Transaction:
    transaction = Transaction(
        reference=f"acme-summary-{run_id}",
        state={
            "run_id": run_id,
            "records": records,
            "omitted_record_count": omitted_record_count,
            "queue_summary": _queue_summary_state(queue_summary),
        },
        metadata={"example": "acme_work_items", "run_id": run_id, "summary": True},
        skills=[WriteSummary(name="write_summary", execution_order=1)],
    )
    engine.run(ProcessContext(transaction=transaction, config=config, credentials=credentials))
    save_transaction(transaction, db_path=str(config["transaction_db_path"]))
    if transaction.status is not Status.SUCCESSFUL:
        raise SystemException("ACME summary transaction failed", action="summary")
    return transaction


def run_example(
    config: dict[str, object],
    *,
    credentials: CredentialProvider | None = None,
    session_factory: Callable[[dict[str, object]], BrowserSession] = _new_browser_session,
    notifiers: list[Notifier] | None = None,
) -> RunResult:
    _validate_config(config)
    provider = credentials or build_credential_provider(str(config["credential_provider"]))
    configured_notifiers = build_notifiers(config, provider) if notifiers is None else notifiers
    queue_config = config["queue"]
    assert isinstance(queue_config, dict)
    queue = SqliteQueue(queue_config)
    run_id = uuid4().hex
    enqueued = scan_inbox(config, queue, provider, session_factory=session_factory)
    engine = Engine(
        max_retries=int(config["max_retries"]),
        retry_delay=float(config["retry_delay"]),
        retry_backoff=float(config["retry_backoff"]),
        screenshot_dir=str(config["screenshot_dir"]),
    )
    records: list[dict[str, object]] = []
    omitted_record_count = 0
    limit = int(config["report_max_records"])

    def after_item(item: QueueItem, transaction: Transaction | None, error: Exception | None) -> None:
        nonlocal omitted_record_count
        if len(records) < limit:
            records.append(_project_outcome(item, transaction, error))
        else:
            omitted_record_count += 1

    queue_summary = run_queue_loop(
        queue,
        engine,
        lambda item: build_transaction(item, run_id=run_id),
        config,
        provider,
        worker_id=f"acme-{run_id[:8]}",
        notifiers=configured_notifiers,
        logger=logger,
        after_item=after_item,
        retry_business_failures=False,
        transaction_db_path=str(config["transaction_db_path"]),
        resource_scope=session_factory(config),
    )
    summary_transaction = _run_summary_transaction(
        config,
        engine,
        run_id=run_id,
        records=records,
        omitted_record_count=omitted_record_count,
        queue_summary=queue_summary,
        credentials=provider,
    )
    return RunResult(run_id, enqueued, queue_summary, summary_transaction)


def main() -> None:
    config = _load_example_config()
    configure_logger(level=str(config["log_level"]), fmt=str(config["log_format"]))
    result = run_example(config)
    logger.info(
        "ACME run complete: enqueued=%d processed=%d completed=%d failed=%d summary=%s",
        result.enqueued,
        result.queue_summary.processed,
        result.queue_summary.completed,
        result.queue_summary.failed,
        result.summary_transaction.state.get("summary_path", ""),
    )


if __name__ == "__main__":
    main()
