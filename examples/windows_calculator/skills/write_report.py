"""RPA Core skill: write test results to a CSV report."""
from __future__ import annotations

import csv
from pathlib import Path

from rpacore import ProcessContext, Skill, Status, SystemException


class WriteReport(Skill):
    """Persist result rows to an output CSV file."""

    FIELDNAMES = ["expression", "expected_result", "actual", "passed"]

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return

        results = ctx.require_state("results", list, action=self.name)
        if not isinstance(results, list):
            raise SystemException("No results in context", action=self.name)

        output_dir = ctx.require_config("output_dir", str, action=self.name)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        report_file = ctx.optional_state("report_file", str, "results.csv", action=self.name)
        source_stem = Path(report_file).stem
        output_file = output_path / f"{source_stem}_results.csv"

        rows: list[dict[str, object]] = []
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                raise SystemException(
                    f"Result at index {index} must be a JSON-safe object",
                    action=self.name,
                )
            rows.append(
                {
                    "expression": result.get("expression", ""),
                    "expected_result": result.get("expected_result", ""),
                    "actual": result.get("actual") or "",
                    "passed": bool(result.get("passed", False)),
                }
            )

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

        pass_count = sum(1 for row in rows if row["passed"])
        fail_count = sum(1 for row in rows if not row["passed"])
        ctx.state["report_path"] = str(output_file)
        ctx.add_artifact(
            name=f"{source_stem}_results.csv",
            path=str(output_file),
            kind="csv",
            metadata={
                "expression_count": len(results),
                "pass_count": pass_count,
                "fail_count": fail_count,
            },
        )
