"""OREF skill: write test results to a CSV report."""
from __future__ import annotations

import csv
from pathlib import Path

from oref import ProcessContext, Skill, Status, SystemException


class WriteReport(Skill):
    """Persist CalculatorResult rows to an output CSV file."""

    FIELDNAMES = ["expression", "expected_result", "actual", "passed"]

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.data.get("validation_failed"):
            self.status = Status.SKIPPED
            return

        results = ctx.data.get("results")
        if not isinstance(results, list):
            raise SystemException("No results in context", action=self.name)

        output_dir = ctx.config.get("output_dir", "output")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        report_file = ctx.data.get("report_file", "results.csv")
        source_stem = Path(report_file).stem
        output_file = output_path / f"{source_stem}_results.csv"

        rows = [
            {
                "expression": r.expression,
                "expected_result": r.expected,
                "actual": r.actual or "",
                "passed": r.passed,
            }
            for r in results
        ]

        try:
            with output_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            raise SystemException(
                f"Unable to write report {output_file}: {exc}",
                action=self.name,
            ) from exc

        ctx.data["report_path"] = str(output_file)
