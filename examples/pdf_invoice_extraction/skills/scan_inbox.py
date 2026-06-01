"""Scan inbox directory and populate the queue with PDF files."""

from __future__ import annotations

import logging
from pathlib import Path

from rpacore import ProcessContext, QueueItem, Skill, SystemException, get_logger

logger = get_logger(__name__)


class ScanInbox(Skill):
    """Scan inbox directory for PDF files and populate the queue.

    Discovers all .pdf files in the sample_data directory, creates queue items
    with file_path and original_name in the payload, and adds them to the queue.

    Expected input keys in ctx.data:
        (none — this is a setup skill that runs before the queue loop)

    Expected arguments (passed via Skill constructor):
        - queue: SqliteQueue — The queue to populate

    Sets on ctx.data:
        - scanned_count: int — Number of PDF files added to the queue
    """

    def execute(self, ctx: ProcessContext) -> None:
        queue = self.arguments.get("queue")
        if queue is None:
            raise SystemException(
                "No queue in arguments — scan_inbox requires a SqliteQueue instance",
                action=self.name,
            )

        sample_data_dir = str(ctx.config.get("sample_data_dir", "sample_data"))
        inbox_path = Path(sample_data_dir)

        if not inbox_path.exists():
            raise SystemException(
                f"Inbox directory does not exist: {sample_data_dir}",
                action=self.name,
            )

        pdf_files = sorted(inbox_path.glob("*.pdf"))
        # Exclude files already in done/ or failed/ subdirectories
        pdf_files = [f for f in pdf_files if f.parent == inbox_path]
        # Skip hidden files
        pdf_files = [f for f in pdf_files if not f.name.startswith(".")]

        if not pdf_files:
            logger.warning("No PDF files found in %s. Nothing to queue.", sample_data_dir)
            ctx.data["scanned_count"] = 0
            return

        added = 0
        for pdf_file in pdf_files:
            queue.add(
                QueueItem(
                    reference=pdf_file.stem,
                    payload={
                        "file_path": str(pdf_file),
                        "original_name": pdf_file.name,
                    },
                ),
            )
            added += 1
            logger.info("Queued: %s", pdf_file.name)

        ctx.data["scanned_count"] = added
        logger.info("Queued %d PDF files from %s", added, sample_data_dir)
