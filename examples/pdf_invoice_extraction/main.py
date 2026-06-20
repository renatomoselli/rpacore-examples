"""PDF Invoice Extraction — queue-driven batch processing example."""

from __future__ import annotations

from pathlib import Path

from rpacore import (
    Engine,
    EnvCredentialProvider,
    QueueItem,
    SqliteQueue,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    resolve_config_paths,
    run_queue_loop,
)

from skills.open_pdf import OpenPdf
from skills.parse_invoice import ParseInvoice
from skills.validate_invoice import ValidateInvoice
from skills.normalize_record import NormalizeRecord
from skills.write_output import WriteOutput

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH_KEYS = (
    "transaction_db_path",
    "sample_data_dir",
    "results_dir",
    "output_csv",
    "queue.db_path",
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

def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("transaction_db_path", str),
        ("sample_data_dir", str),
        ("results_dir", str),
        ("output_csv", str),
        ("max_pages", int),
    ):
        if key not in config:
            raise SystemException(f"Missing required config key: {key}", action="main")
        if not isinstance(config[key], expected_type):
            raise SystemException(
                f"Config key '{key}' must be {expected_type.__name__}, got {type(config[key]).__name__}",
                action="main",
            )
    if config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'max_retries' must be >= 0, got {config['max_retries']}",
            action="main",
        )
    if config["max_pages"] < 1:
        raise SystemException(
            f"Config key 'max_pages' must be >= 1, got {config['max_pages']}",
            action="main",
        )
    if not config["output_csv"]:
        raise SystemException(
            "Config key 'output_csv' must be a non-empty string",
            action="main",
        )

    queue_config = config.get("queue")
    if not isinstance(queue_config, dict):
        raise SystemException("Missing required [queue] config section", action="main")

    for key in ("db_path", "lease_timeout", "max_retries"):
        if key not in queue_config:
            raise SystemException(
                f"Missing required [queue] config key: {key}", action="main"
            )

    if not isinstance(queue_config["db_path"], str) or not queue_config["db_path"]:
        raise SystemException(
            "Config key 'queue.db_path' must be a non-empty string", action="main"
        )
    if not isinstance(queue_config["lease_timeout"], int) or queue_config["lease_timeout"] <= 0:
        raise SystemException(
            f"Config key 'queue.lease_timeout' must be a positive int, got {queue_config['lease_timeout']!r}",
            action="main",
        )
    if not isinstance(queue_config["max_retries"], int) or queue_config["max_retries"] < 0:
        raise SystemException(
            f"Config key 'queue.max_retries' must be a non-negative int, got {queue_config['max_retries']!r}",
            action="main",
        )

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

    pdf_files = sorted(inbox_path.glob("*.pdf"))
    # Skip hidden files
    pdf_files = [f for f in pdf_files if not f.name.startswith(".")]

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
        skills=[
            OpenPdf(name="open_pdf", execution_order=1),
            ParseInvoice(name="parse_invoice", execution_order=2),
            ValidateInvoice(name="validate_invoice", execution_order=3),
            NormalizeRecord(name="normalize_record", execution_order=4),
            WriteOutput(name="write_output", execution_order=5),
        ],
    )

def main() -> None:
    config = load_config(str(PROJECT_ROOT / "config.toml"))
    _validate_config(config)
    config = resolve_config_paths(
        config,
        _CONFIG_PATH_KEYS,
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )
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
        "Queue processing complete: processed=%d completed=%d failed=%d",
        summary.processed,
        summary.completed,
        summary.failed,
    )

if __name__ == "__main__":
    main()
