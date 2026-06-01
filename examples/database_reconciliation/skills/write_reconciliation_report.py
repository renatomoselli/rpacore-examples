from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException

REPORT_COLUMNS = (
    "payment_id",
    "date",
    "reference",
    "vendor",
    "internal_amount",
    "bank_amount",
    "bank_date",
    "status",
    "reason_code",
)


class WriteReconciliationReport(Skill):
    """Write a deterministic reconciliation summary CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        results = ctx.data.get("reconciliation_results")
        if not isinstance(results, list):
            raise SystemException("No reconciliation_results in context", action=self.name)

        report_file = ctx.config.get("report_file")
        if not isinstance(report_file, str) or not report_file:
            raise SystemException("Config key 'report_file' must be a non-empty string", action=self.name)

        path = Path(report_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
                writer.writeheader()
                for result in results:
                    writer.writerow({column: str(result.get(column, "")) for column in REPORT_COLUMNS})
            temp_path.replace(path)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise SystemException(f"Unable to write reconciliation report {path}: {exc}", action=self.name) from exc

        ctx.data["report_file"] = str(path)
