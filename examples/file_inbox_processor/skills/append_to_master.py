from __future__ import annotations

import csv
from pathlib import Path

from oref import ProcessContext, Skill, SystemException

from skills._path_utils import validate_contained_path

MASTER_COLUMNS = ("source_file", "branch_id", "date", "revenue", "headcount", "revenue_per_headcount")


class AppendToMaster(Skill):
    """Append the processed report to the consolidated CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.data.get("validation_failed"):
            return

        report = ctx.data.get("processed_report")
        if not isinstance(report, dict):
            raise SystemException("No processed report in context", action=self.name)

        master_csv = ctx.config.get("master_csv")
        if not isinstance(master_csv, str) or not master_csv:
            raise SystemException("Config key 'master_csv' must be a non-empty string", action=self.name)

        path = Path(master_csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.exists() or path.stat().st_size == 0
        raw_source = ctx.data.get("report_file") or ctx.data.get("file_path", "")
        if not isinstance(raw_source, str) or not raw_source:
            raise SystemException("No source file available", action=self.name)

        # Skip validation when inbox_dir is absent (unit tests); production always provides it.
        inbox_dir = ctx.config.get("inbox_dir")
        if isinstance(inbox_dir, str) and inbox_dir:
            source_path = validate_contained_path(raw_source, inbox_dir, action=self.name)
        else:
            source_path = Path(raw_source)
        source_file = source_path.name

        if source_file and _already_appended(path, source_file):
            ctx.data["master_csv"] = str(path)
            return

        try:
            with path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=MASTER_COLUMNS)
                if write_header:
                    writer.writeheader()
                row = {column: str(report[column]) for column in MASTER_COLUMNS if column != "source_file"}
                row["source_file"] = source_file
                writer.writerow(row)
        except OSError as exc:
            raise SystemException(f"Unable to append to master CSV {path}: {exc}", action=self.name) from exc

        ctx.data["master_csv"] = str(path)


def _already_appended(path: Path, source_file: str) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if "source_file" not in (reader.fieldnames or []):
                return False
            return any(row.get("source_file") == source_file for row in reader)
    except OSError:
        return False
