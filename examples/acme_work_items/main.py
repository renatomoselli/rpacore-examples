from __future__ import annotations

"""ACME Work Items — durable queue-driven browser automation capstone."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from uuid import uuid4

from rpacore import (
    BusinessException,
    ConfigField,
    CredentialProvider,
    Engine,
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
    execute_transaction,
    generate_report,
    get_logger,
    load_config,
    resolve_config_paths,
    run_queue_loop,
    validate_config,
)

from steps._session import BrowserSession, DiscoveredItem, validate_work_item_id
from steps.close_work_item import CloseWorkItem
from steps.compute_security_hash import ComputeSecurityHash
from steps.fetch_work_item import FetchWorkItem
from steps.update_work_item import UpdateWorkItem
from steps.validate_work_item import ValidateWorkItem
from steps.write_summary import WriteSummary


logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
ITEM_DEFINITION_IDENTITY = "acme-work-items/item/v1"
SUMMARY_DEFINITION_IDENTITY = "acme-work-items/summary/v1"
_CONFIG_PATH_KEYS = (
    "transaction_db_path",
    "queue.db_path",
    "screenshot_dir",
    "report_dir",
)
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_QUEUE_SUMMARY_FIELDS = (
    "processed",
    "completed",
    "failed",
    "callback_errors",
    "persistence_errors",
    "lifecycle_errors",
    "notification_errors",
    "retry_scheduled",
    "terminal_failed",
    "lease_lost",
    "transition_unknown",
)
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("retry_delay", (int, float), min_value=0),
    ConfigField("retry_backoff", (int, float), min_value=1),
    ConfigField("log_level", str, allow_empty=False),
    ConfigField("log_format", str, choices=("text", "json")),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("screenshot_dir", str, allow_empty=False),
    ConfigField("report_dir", str, allow_empty=False),
    ConfigField("report_max_records", int, min_value=1),
    ConfigField("base_url", str, allow_empty=False),
    ConfigField("credential_provider", str, choices=("env", "keyring")),
    ConfigField("headless", bool),
    ConfigField("page_load_timeout_ms", int, min_value=1),
    ConfigField("action_timeout_ms", int, min_value=1),
    ConfigField("queue.db_path", str, allow_empty=False),
    ConfigField("queue.lease_timeout", int, min_value=1),
    ConfigField("queue.max_retries", int, min_value=0),
)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    enqueued: int
    queue_summary: QueueRunSummary
    summary_transaction: Transaction


def _validate_config(config: dict[str, object]) -> None:
    try:
        validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc

    for key in ("transaction_db_path", "screenshot_dir", "report_dir"):
        if not str(config[key]).strip():
            raise SystemException(f"{key} must be a non-empty path", action="main")

    if str(config["log_level"]).upper() not in _LOG_LEVELS:
        raise SystemException("log_level is invalid", action="main")

    parsed = urlparse(str(config["base_url"]))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemException("base_url must be an absolute HTTP(S) URL", action="main")
    if parsed.username or parsed.password:
        raise SystemException("base_url must not contain embedded credentials", action="main")

    queue_config = config["queue"]
    if not isinstance(queue_config, dict):
        raise SystemException("queue must be a configuration table", action="main")
    if not str(queue_config["db_path"]).strip():
        raise SystemException("queue.db_path must be non-empty", action="main")


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
    if not isinstance(item.payload, dict):
        raise SystemException("Queue payload must be an object", action="build_transaction")
    payload_keys = set(item.payload)
    if not {"work_item_id", "discovered_hash"} <= payload_keys:
        raise SystemException("Queue payload must contain work_item_id and discovered_hash", action="build_transaction")
    if "work_item_url" in payload_keys:
        raise SystemException("Queue payload must not supply a work_item_url", action="build_transaction")
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
        definition_identity=ITEM_DEFINITION_IDENTITY,
        metadata={"example": "acme_work_items", "work_item_id": work_item_id, "run_id": run_id},
        steps=[
            FetchWorkItem(name="fetch_work_item", execution_order=1),
            ValidateWorkItem(name="validate_work_item", execution_order=2),
            ComputeSecurityHash(name="compute_security_hash", execution_order=3),
            UpdateWorkItem(name="update_work_item", execution_order=4),
            CloseWorkItem(name="close_work_item", execution_order=5),
        ],
    )


def _failure_diagnostics(transaction: Transaction | None, error: Exception | None) -> dict[str, str]:
    failed_step = ""
    exception: BaseException | None = error
    if transaction is not None:
        failed = transaction.failed_steps()
        if failed:
            failed_step = failed[-1].name
            if failed[-1].exceptions:
                exception = failed[-1].exceptions[-1]
    if isinstance(exception, BusinessException):
        return {"failed_step": failed_step, "error_type": "business_exception", "message": str(exception)[:300]}
    if isinstance(exception, SystemException):
        return {"failed_step": failed_step, "error_type": "system_exception", "message": str(exception)[:300]}
    if exception is not None:
        return {
            "failed_step": failed_step,
            "error_type": "unexpected_exception",
            "message": "Unexpected item-processing error",
        }
    return {"failed_step": failed_step} if failed_step else {}


def _project_outcome(
    item: QueueItem,
    transaction: Transaction | None,
    error: Exception | None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "work_item_id": item.payload.get("work_item_id", ""),
        "queue_reference": item.reference,
        "queue_retry_count": item.retry_count,
    }
    if transaction is not None:
        report = generate_report(transaction)
        if report.record is None:
            raise SystemException("Unable to create canonical transaction report record", action="summary")
        record.update(
            {
                "transaction_id": transaction.id,
                "transaction_status": str(transaction.status),
                "transaction_retry_count": report.retry_count,
                "outcome": {
                    "category": str(report.outcome.category),
                    "retry_disposition": str(report.outcome.retry_disposition),
                    "failure_code": report.outcome.failure_code,
                },
                "report_record": report.record.to_dict(),
                "idempotency_outcome": transaction.state.get("idempotency_outcome", ""),
                "artifact_paths": [artifact.path for artifact in transaction.artifacts],
            }
        )
    diagnostics = _failure_diagnostics(transaction, error)
    if diagnostics:
        record["diagnostics"] = diagnostics
    return record


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
        definition_identity=SUMMARY_DEFINITION_IDENTITY,
        state={
            "run_id": run_id,
            "records": records,
            "omitted_record_count": omitted_record_count,
            "queue_summary": _queue_summary_state(queue_summary),
        },
        metadata={"example": "acme_work_items", "run_id": run_id, "summary": True},
        steps=[WriteSummary(name="write_summary", execution_order=1)],
    )
    execute_transaction(
        transaction,
        config=config,
        credentials=credentials,
        engine=engine,
        transaction_db_path=str(config["transaction_db_path"]),
    )
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
    if not isinstance(queue_config, dict):
        raise SystemException("queue must be a configuration table", action="main")
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


def _log_run_summary(result: RunResult) -> None:
    logger.info(
        "ACME run complete.",
        extra={
            "event": "acme_run_summary",
            "run_id": result.run_id,
            "enqueued": result.enqueued,
            "summary_transaction_id": result.summary_transaction.id,
            "summary_transaction_reference": result.summary_transaction.reference,
            **{
                field: getattr(result.queue_summary, field)
                for field in _QUEUE_SUMMARY_FIELDS
            },
        },
    )


def main() -> None:
    config = _load_example_config()
    log_format = str(config["log_format"])
    logger_options: dict[str, object] = {"level": str(config["log_level"]), "fmt": log_format}
    configure_logger(**logger_options)
    result = run_example(config)
    _log_run_summary(result)


if __name__ == "__main__":
    main()
