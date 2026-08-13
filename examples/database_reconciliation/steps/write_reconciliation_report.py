from __future__ import annotations

import csv
from pathlib import Path

from rpacore import ProcessContext, Step, SystemException, atomic_output_path

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


class WriteReconciliationReport(Step):
    """Write a deterministic reconciliation summary CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        results = ctx.require_state("reconciliation_results", list, action=self.name)
        report_file = ctx.require_config("report_file", str, action=self.name)
        if not report_file:
            raise SystemException("Config key 'report_file' must be a non-empty string", action=self.name)

        path = Path(report_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with atomic_output_path(path) as temporary:
                with temporary.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
                    writer.writeheader()
                    for result in results:
                        writer.writerow({column: str(result.get(column, "")) for column in REPORT_COLUMNS})
        except OSError as exc:
            raise SystemException(f"Unable to write reconciliation report {path}: {exc}", action=self.name) from exc

        ctx.add_artifact(
            name="reconciliation_report",
            path=str(path),
            kind="csv",
            metadata={
                "record_count": len(results),
                "status_counts": {
                    "matched": sum(1 for r in results if r.get("status") == "matched"),
                    "missing_from_bank": sum(1 for r in results if r.get("status") == "missing_from_bank"),
                    "amount_mismatch": sum(1 for r in results if r.get("status") == "amount_mismatch"),
                    "type_error": sum(1 for r in results if r.get("status") == "type_error"),
                },
            },
        )
