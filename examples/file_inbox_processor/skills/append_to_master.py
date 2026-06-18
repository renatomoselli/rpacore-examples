from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import csv
import os
from pathlib import Path
import time

from rpacore import ProcessContext, Skill, Status, SystemException

from skills._path_utils import validate_contained_path

MASTER_COLUMNS = ("source_file", "branch_id", "date", "revenue", "headcount", "revenue_per_headcount")
MASTER_LOCK_TIMEOUT_SECONDS = 10.0
MASTER_LOCK_POLL_SECONDS = 0.05


class AppendToMaster(Skill):
    """Append the processed report to the consolidated CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return

        report = ctx.require_state("processed_report", dict, action=self.name)
        if not isinstance(report, dict):
            raise SystemException("No processed report in context", action=self.name)

        master_csv = ctx.require_config("master_csv", str, action=self.name)
        if not master_csv:
            raise SystemException("Config key 'master_csv' must be a non-empty string", action=self.name)

        path = Path(master_csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw_source = ctx.optional_state("report_file", str, "", action=self.name) or ctx.optional_state(
            "file_path",
            str,
            "",
            action=self.name,
        )
        if not isinstance(raw_source, str) or not raw_source:
            raise SystemException("No source file available", action=self.name)

        # Skip validation when inbox_dir is absent (unit tests); production always provides it.
        inbox_dir = ctx.config.get("inbox_dir")
        if isinstance(inbox_dir, str) and inbox_dir:
            source_path = validate_contained_path(raw_source, inbox_dir, action=self.name)
        else:
            source_path = Path(raw_source)
        source_file = source_path.name

        with _master_csv_lock(path):
            if source_file and _already_appended(path, source_file):
                ctx.state["master_csv"] = str(path)
                ctx.add_artifact("master_csv", str(path), kind="csv", metadata={"source_file": source_file})
                return

            try:
                with path.open("a", encoding="utf-8", newline="") as handle:
                    write_header = handle.tell() == 0
                    writer = csv.DictWriter(handle, fieldnames=MASTER_COLUMNS)
                    if write_header:
                        writer.writeheader()
                    row = {column: str(report[column]) for column in MASTER_COLUMNS if column != "source_file"}
                    row["source_file"] = source_file
                    writer.writerow(row)
            except OSError as exc:
                raise SystemException(f"Unable to append to master CSV {path}: {exc}", action=self.name) from exc

        ctx.state["master_csv"] = str(path)
        ctx.add_artifact("master_csv", str(path), kind="csv", metadata={"source_file": source_file})


def _already_appended(path: Path, source_file: str) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if "source_file" not in (reader.fieldnames or []):
                return False
            return any(row.get("source_file") == source_file for row in reader)
    except OSError as exc:
        raise SystemException(
            f"Unable to inspect master CSV {path}: {exc}",
            action="append_to_master",
        ) from exc


@contextmanager
def _master_csv_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    deadline = time.monotonic() + MASTER_LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SystemException(
                    f"Timed out waiting for master CSV lock: {lock_path}",
                    action="append_to_master",
                ) from exc
            time.sleep(MASTER_LOCK_POLL_SECONDS)
        except OSError as exc:
            raise SystemException(
                f"Unable to lock master CSV {path}: {exc}",
                action="append_to_master",
            ) from exc

    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise SystemException(
                f"Unable to remove master CSV lock {lock_path}: {exc}",
                action="append_to_master",
            ) from exc
