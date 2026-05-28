"""PDF Invoice Extraction — queue-driven batch processing example."""

from __future__ import annotations

from pathlib import Path

from oref import (
    Engine,
    EnvCredentialProvider,
    ProcessContext,
    QueueItem,
    SqliteQueue,
    SystemException,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    run_queue_loop,
)

from skills.open_pdf import OpenPdf
from skills.parse_invoice import ParseInvoice
from skills.validate_invoice import ValidateInvoice
from skills.normalize_record import NormalizeRecord
from skills.write_output import WriteOutput
from skills.scan_inbox import ScanInbox

logger = get_logger(__name__)


def _validate_config(config: dict) -> None:
    """Validate config has required keys with correct types and ranges."""
    for key, expected_type in (
        ("max_retries", int),
        ("log_level", str),
        ("db_path", str),
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
    for dir_key in ("sample_data_dir", "results_dir"):
        dir_path = config[dir_key]
        if not isinstance(dir_path, str) or not dir_path:
            raise SystemException(
                f"Config key '{dir_key}' must be a non-empty string",
                action="main",
            )


def build_transaction(item: QueueItem) -> Transaction:
    """Build a transaction for each queued PDF invoice."""
    return Transaction(
        reference=f"invoice-{item.payload.get('original_name', 'unknown')}",
        skills=[
            OpenPdf(name="open_pdf", execution_order=1),
            ParseInvoice(name="parse_invoice", execution_order=2),
            ValidateInvoice(name="validate_invoice", execution_order=3),
            NormalizeRecord(name="normalize_record", execution_order=4),
            WriteOutput(name="write_output", execution_order=5),
        ],
    )


def main() -> None:
    config = load_config("config.toml")
    _validate_config(config)
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    queue = SqliteQueue(config)

    # Setup: scan inbox and populate queue
    scan_ctx = ProcessContext(
        transaction=Transaction(reference="scan-inbox", skills=[]),
        config=config,
        data={},
    )
    scan_skill = ScanInbox(
        name="scan_inbox",
        execution_order=1,
        arguments={"queue": queue},
    )
    scan_skill.execute(scan_ctx)
    scanned = scan_ctx.data.get("scanned_count", 0)
    logger.info("Scanned %d PDF files from %s", scanned, config["sample_data_dir"])

    if scanned == 0:
        logger.warning("No PDF files to process. Exiting.")
        return

    # Drain queue via run_queue_loop
    run_queue_loop(
        queue=queue,
        engine=engine,
        build_transaction=build_transaction,
        config=config,
        credentials=EnvCredentialProvider(),
    )

    logger.info("Queue processing complete.")


if __name__ == "__main__":
    main()
