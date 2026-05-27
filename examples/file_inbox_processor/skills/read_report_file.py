from __future__ import annotations

import csv
from pathlib import Path

from oref import ProcessContext, Skill, SystemException


class ReadReportFile(Skill):
    """Read a single branch CSV report from the queue payload."""

    def execute(self, ctx: ProcessContext) -> None:
        file_path = ctx.data.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise SystemException("Queue item payload missing file_path", action=self.name)

        path = Path(file_path)
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            raise SystemException(
                f"Unable to read report file {path}: {exc}",
                action=self.name,
            ) from exc

        ctx.data["report_file"] = str(path)
        ctx.data["report_rows"] = rows
        ctx.data["report_columns"] = list(rows[0].keys()) if rows else []
