"""Write normalized invoice records to CSV and move source files."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rpacore import BusinessException, ProcessContext, Skill, Status, SystemException, get_logger

logger = get_logger(__name__)

_CSV_HEADER = [
    "invoice_number",
    "date",
    "vendor",
    "line_items_count",
    "subtotal",
    "total",
    "currency",
]
_CSV_LOCK_TIMEOUT_SECONDS = 10.0
_CSV_LOCK_POLL_SECONDS = 0.05
_CSV_LOCK_STALE_SECONDS = 60.0


class WriteOutput(Skill):
    """Write normalized invoice record to CSV output and move the source PDF to done/.

    On success: moves PDF to done/, atomically appends record to CSV, and registers artifacts.
    On duplicate: raises BusinessException (stop=True) for duplicate invoice numbers.
    """

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            logger.info("Validation failed earlier; skipping output write.")
            self.status = Status.SKIPPED
            return

        normalized_record = ctx.require_state("normalized_record", dict, action=self.name)
        file_path = ctx.require_state("file_path", str, action=self.name)

        results_dir = str(ctx.config.get("results_dir", "results"))
        output_csv = str(ctx.config.get("output_csv", "results/output.csv"))
        sample_data_dir = str(ctx.config.get("sample_data_dir", "sample_data"))

        Path(results_dir).mkdir(parents=True, exist_ok=True)
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "done")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(sample_data_dir, "failed")).mkdir(parents=True, exist_ok=True)

        original_name = ctx.optional_state(
            "original_name", str, Path(file_path).name, action=self.name
        )
        with _output_csv_lock(Path(output_csv), action=self.name):
            dest_path = self._move_source_and_write(
                ctx,
                normalized_record,
                file_path,
                original_name,
                sample_data_dir,
                output_csv,
            )
        ctx.state["output_written"] = True

        ctx.add_artifact(
            "invoice_csv",
            output_csv,
            kind="csv",
            metadata={
                "invoice_number": normalized_record.get("invoice_number", ""),
                "vendor": normalized_record.get("vendor", ""),
                "source_file": original_name,
            },
        )
        if dest_path is not None:
            ctx.add_artifact(
                "source_pdf",
                dest_path,
                kind="pdf",
                metadata={
                    "invoice_number": normalized_record.get("invoice_number", ""),
                    "source_file": original_name,
                },
            )

        logger.info(
            "Wrote invoice %s to %s",
            normalized_record.get("invoice_number", "unknown"),
            output_csv,
        )

    def _move_source_and_write(
        self,
        ctx: ProcessContext,
        normalized_record: dict,
        file_path: str,
        original_name: str,
        sample_data_dir: str,
        output_csv: str,
    ) -> str | None:
        """Check, move, and write while the output CSV lock is held."""
        rows = self._read_csv_rows(output_csv)
        self._raise_if_duplicate(
            rows,
            str(normalized_record.get("invoice_number", "")),
        )
        dest_path = ctx.optional_state("done_path", str, "", action=self.name) or None
        moved_this_run = False
        if os.path.exists(file_path):
            if dest_path is None:
                dest_path = self._find_unique_dest(sample_data_dir, "done", original_name)
                ctx.state["done_path"] = dest_path
            try:
                shutil.move(file_path, dest_path)
                moved_this_run = True
            except OSError as exc:
                raise SystemException(
                    f"Failed to move PDF to done/: {exc}",
                    action=self.name,
                ) from exc
            logger.info("Moved PDF to done/: %s", original_name)
        else:
            logger.info("Source PDF not found, skipping move: %s", file_path)

        try:
            self._write_csv_record(output_csv, normalized_record, rows)
        except SystemException:
            if moved_this_run and dest_path is not None:
                self._restore_source_pdf(dest_path, file_path, ctx)
            raise
        return dest_path

    def _write_csv_record(
        self,
        output_csv: str,
        invoice: dict,
        rows: list[dict[str, str]] | None = None,
    ) -> None:
        """Append a single invoice record using an atomic CSV replacement."""
        if rows is None:
            rows = self._read_csv_rows(output_csv)
            self._raise_if_duplicate(rows, str(invoice.get("invoice_number", "")))
        rows.append(self._csv_row(invoice))
        self._replace_csv(output_csv, rows)

    def _read_csv_rows(self, output_csv: str) -> list[dict[str, str]]:
        """Read existing CSV rows, treating malformed output as retryable."""
        if not os.path.exists(output_csv):
            return []

        try:
            with open(output_csv, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != _CSV_HEADER:
                    raise BusinessException(
                        f"Unexpected CSV header: {reader.fieldnames!r}",
                        action=self.name,
                        stop=True,
                    )
                return [dict(row) for row in reader]
        except (csv.Error, OSError) as exc:
            raise SystemException(
                f"Could not read existing CSV output {output_csv}: {exc}",
                action=self.name,
            ) from exc

    def _replace_csv(self, output_csv: str, rows: list[dict[str, str]]) -> None:
        """Atomically replace the CSV with the supplied rows."""
        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=str(output_path.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temp_path, output_path)
        except OSError as exc:
            raise SystemException(
                f"Could not update CSV output {output_csv}: {exc}",
                action=self.name,
            ) from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _restore_source_pdf(
        self, dest_path: str, original_path: str, ctx: ProcessContext
    ) -> None:
        """Move a just-processed PDF back to the inbox after CSV failure."""
        if os.path.exists(original_path) or not os.path.exists(dest_path):
            return
        try:
            shutil.move(dest_path, original_path)
            ctx.state.pop("done_path", None)
            logger.info("Restored PDF to inbox after CSV failure: %s", original_path)
        except OSError as exc:
            # Keep done_path so a retry can recover the PDF artifact from its
            # actual location even though the inbox restoration failed.
            raise SystemException(
                f"Failed to restore PDF after CSV failure: {exc}",
                action=self.name,
            ) from exc

    def _csv_row(self, invoice: dict) -> dict[str, str]:
        """Return a normalized CSV row for an invoice."""
        return {
            "invoice_number": str(invoice.get("invoice_number", "")),
            "date": str(invoice.get("date", "")),
            "vendor": str(invoice.get("vendor", "")),
            "line_items_count": str(
                invoice.get("line_items_count", len(invoice.get("line_items", [])))
            ),
            "subtotal": self._format_decimal(invoice.get("subtotal")),
            "total": self._format_decimal(invoice.get("total")),
            "currency": str(invoice.get("currency", "USD")),
        }

    def _raise_if_duplicate(self, rows: list[dict[str, str]], invoice_number: str) -> None:
        """Raise BusinessException when invoice_number already exists."""
        if not invoice_number:
            raise BusinessException(
                "Missing invoice number for output",
                action=self.name,
                stop=True,
            )
        for row in rows:
            if row.get("invoice_number") == invoice_number:
                raise BusinessException(
                    f"Duplicate invoice number: {invoice_number}",
                    action=self.name,
                    stop=True,
                )

    @staticmethod
    def _format_decimal(value: float | int | None) -> str:
        """Format a decimal value for CSV output."""
        if value is None:
            return ""
        return f"{float(value):.2f}"

    @staticmethod
    def _find_unique_dest(sample_data_dir: str, destination: str, name: str) -> str:
        """Find a unique destination path, appending a timestamp suffix if needed."""
        dest_dir = os.path.join(sample_data_dir, destination)
        dest_path = os.path.join(dest_dir, name)

        if not os.path.exists(dest_path):
            return dest_path

        stem, ext = os.path.splitext(name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}{ext}")

        if not os.path.exists(dest_path):
            return dest_path

        for counter in range(1, 1001):
            dest_path = os.path.join(dest_dir, f"{stem}_{timestamp}_{counter}{ext}")
            if not os.path.exists(dest_path):
                return dest_path
        raise SystemException(
            f"Could not find a unique destination for {name} after 1000 attempts",
            action="write_output",
        )


@contextmanager
def _output_csv_lock(path: Path, *, action: str) -> Iterator[None]:
    """Serialize duplicate checks and CSV publication across worker processes."""
    lock_path = path.with_name(f"{path.name}.lock")
    deadline = time.monotonic() + _CSV_LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if _remove_stale_lock(lock_path, action=action):
                continue
            if time.monotonic() >= deadline:
                raise SystemException(
                    f"Timed out waiting for output CSV lock: {lock_path}",
                    action=action,
                ) from exc
            time.sleep(_CSV_LOCK_POLL_SECONDS)
        except OSError as exc:
            raise SystemException(
                f"Unable to lock output CSV {path}: {exc}",
                action=action,
            ) from exc

    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError as exc:
            logger.warning("Unable to close output CSV lock descriptor: %s", exc)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise SystemException(
                f"Unable to remove output CSV lock {lock_path}: {exc}",
                action=action,
            ) from exc


def _remove_stale_lock(lock_path: Path, *, action: str) -> bool:
    """Remove a crash-left sidecar after a conservative staleness window."""
    try:
        age_seconds = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise SystemException(
            f"Unable to inspect output CSV lock {lock_path}: {exc}",
            action=action,
        ) from exc

    if age_seconds <= _CSV_LOCK_STALE_SECONDS:
        return False

    try:
        lock_path.unlink()
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise SystemException(
            f"Unable to remove stale output CSV lock {lock_path}: {exc}",
            action=action,
        ) from exc

    logger.warning(
        "Removed stale output CSV lock %s (age %.1fs).",
        lock_path,
        age_seconds,
    )
    return True
