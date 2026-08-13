"""PDF Invoice Extraction — queue-driven batch processing example."""

from __future__ import annotations

from pathlib import Path

from rpacore import (
    ConfigField,
    Engine,
    EnvCredentialProvider,
    QueueItem,
    QueueRunSummary,
    SqliteQueue,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    run_queue_loop,
    validate_config,
)

from steps.open_pdf import OpenPdf
from steps.parse_invoice import ParseInvoice
from steps.validate_invoice import ValidateInvoice
from steps.normalize_record import NormalizeRecord
from steps.write_output import WriteOutput

logger = get_logger(__name__)
DEFINITION_IDENTITY = "pdf-invoice-extraction/invoice/v1"
PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH_KEYS = (
    "transaction_db_path",
    "sample_data_dir",
    "results_dir",
    "output_csv",
    "queue.db_path",
)
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField(
        "log_level",
        str,
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        allow_empty=False,
    ),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("sample_data_dir", str, allow_empty=False),
    ConfigField("results_dir", str, allow_empty=False),
    ConfigField("output_csv", str, allow_empty=False),
    ConfigField("max_pages", int, min_value=1),
    ConfigField("queue.db_path", str, allow_empty=False),
    ConfigField("queue.lease_timeout", int, min_value=1),
    ConfigField("queue.max_retries", int, min_value=0),
)
_SUMMARY_FIELDS = (
    "processed", "completed", "failed", "callback_errors", "persistence_errors",
    "lifecycle_errors", "notification_errors", "retry_scheduled", "terminal_failed",
    "lease_lost", "transition_unknown",
)

def _has_sample_pdfs(sample_data_dir: str) -> bool:
    """Return True when the inbox or a disposition directory contains PDFs."""
    sample_path = Path(sample_data_dir)
    if not sample_path.exists():
        return False

    # Completed or failed demo inputs suppress regeneration, while unrelated
    # nested folders are not treated as processable inbox content.
    for directory in (sample_path, sample_path / "done", sample_path / "failed"):
        if directory.exists() and any(
            pdf_file.is_file() and not pdf_file.name.startswith(".")
            for pdf_file in directory.glob("*.pdf")
        ):
            return True
    return False

def _validate_config(config: dict[str, object]) -> None:
    """Validate public field contracts and explicit whitespace domain rules."""
    try:
        validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc
    for key in (
        "log_level", "transaction_db_path", "sample_data_dir", "results_dir", "output_csv",
    ):
        value = config[key]
        if not isinstance(value, str) or not value.strip():
            raise SystemException(f"Config key '{key}' must be a non-empty string", action="main")
    queue = config["queue"]
    if not isinstance(queue, dict):
        raise SystemException("Config key 'queue' must be a table", action="main")
    db_path = queue["db_path"]
    if not isinstance(db_path, str) or not db_path.strip():
        raise SystemException("Config key 'queue.db_path' must be a non-empty string", action="main")


def _load_example_config() -> dict[str, object]:
    config = load_config(PROJECT_ROOT / "config.toml", require_file=True)
    _validate_config(config)
    return resolve_config_paths(config, _CONFIG_PATH_KEYS, base_dir=PROJECT_ROOT, root=PROJECT_ROOT)


def _summary_values(summary: QueueRunSummary) -> dict[str, int]:
    return {field: getattr(summary, field) for field in _SUMMARY_FIELDS}

def ensure_sample_data(config: dict) -> None:
    """Generate demo invoices when a fresh checkout has no input PDFs."""
    sample_data_dir = str(config["sample_data_dir"])
    if _has_sample_pdfs(sample_data_dir):
        return

    logger.info("No sample PDFs found in %s; generating demo invoices.", sample_data_dir)
    from generate_sample_data import generate_sample_data

    generate_sample_data(sample_data_dir)

def scan_inbox(config: dict, queue: SqliteQueue) -> int:
    """Add new PDF files in the sample_data directory as queue items."""
    sample_data_dir = str(config["sample_data_dir"])
    inbox_path = Path(sample_data_dir)

    if not inbox_path.exists():
        raise SystemException(
            f"Inbox directory does not exist: {sample_data_dir}",
            action="scan_inbox",
        )

    inbox_root = inbox_path.resolve()
    pdf_files = []
    for pdf_file in sorted(inbox_path.glob("*.pdf")):
        if pdf_file.name.startswith("."):
            continue
        resolved = pdf_file.resolve()
        if not resolved.is_relative_to(inbox_root):
            logger.warning("Skipping inbox PDF outside configured root: %s", pdf_file.name)
            continue
        pdf_files.append(pdf_file)

    if not pdf_files:
        logger.warning("No PDF files found in %s. Nothing to queue.", sample_data_dir)
        return 0

    count = 0
    for pdf_file in pdf_files:
        reference = pdf_file.stem
        added = queue.add_once(
            QueueItem(
                reference=reference,
                payload={
                    "file_path": str(pdf_file),
                    "original_name": pdf_file.name,
                },
            ),
        )
        if added:
            count += 1
            logger.info("Queued: %s", pdf_file.name)

    logger.info("Queued %d PDF files from %s", count, sample_data_dir)
    return count

def build_transaction(item: QueueItem) -> Transaction:
    """Build a transaction for each queued PDF invoice."""
    original_name = item.payload.get("original_name")
    if not isinstance(original_name, str) or not original_name:
        raise SystemException(
            "Queue item payload requires a non-empty original_name",
            action="build_transaction",
        )
    return Transaction(
        reference=f"invoice-{original_name}",
        definition_identity=DEFINITION_IDENTITY,
        steps=[
            OpenPdf(name="open_pdf", execution_order=1),
            ParseInvoice(name="parse_invoice", execution_order=2),
            ValidateInvoice(name="validate_invoice", execution_order=3),
            NormalizeRecord(name="normalize_record", execution_order=4),
            WriteOutput(name="write_output", execution_order=5),
        ],
    )

def main() -> None:
    config = _load_example_config()
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    queue = SqliteQueue(config["queue"])

    ensure_sample_data(config)

    # Setup: scan inbox and populate queue
    scanned = scan_inbox(config, queue)
    logger.info("Scanned %d PDF files from %s", scanned, config["sample_data_dir"])

    # Drain queue via run_queue_loop. Even when scan_inbox adds no new items,
    # existing pending work may already be present from an earlier interrupted run.
    summary = run_queue_loop(
        queue=queue,
        engine=engine,
        build_transaction=build_transaction,
        config=config,
        credentials=EnvCredentialProvider(),
        transaction_db_path=str(config["transaction_db_path"]),
    )

    logger.info(
        "Queue processing complete: %s",
        " ".join(f"{field}={value}" for field, value in _summary_values(summary).items()),
    )

if __name__ == "__main__":
    main()
