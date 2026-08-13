from __future__ import annotations

import csv
from pathlib import Path

from rpacore import ProcessContext, Step, SystemException, resolve_config_path


class ReadReportFile(Step):
    """Read a single branch CSV report from the queue payload."""

    def execute(self, ctx: ProcessContext) -> None:
        file_path = ctx.require_state("file_path", str, action=self.name)
        if not file_path:
            raise SystemException("Queue item payload missing file_path", action=self.name)

        # Skip validation when inbox_dir is absent (unit tests); production always provides it.
        inbox_dir = ctx.config.get("inbox_dir")
        if isinstance(inbox_dir, str) and inbox_dir:
            path = Path(
                resolve_config_path(
                    file_path,
                    base_dir=inbox_dir,
                    root=inbox_dir,
                    key=self.name,
                )
            )
        else:
            path = Path(file_path)

        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            raise SystemException(
                f"Unable to read report file {path}: {exc}",
                action=self.name,
            ) from exc

        ctx.state["report_file"] = str(path)
        ctx.state["report_rows"] = rows
        ctx.state["report_columns"] = list(rows[0].keys()) if rows else []
        ctx.transaction.metadata["source_file"] = path.name
