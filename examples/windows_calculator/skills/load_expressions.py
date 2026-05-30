"""OREF skill: load test expressions from a CSV file."""
from __future__ import annotations

import csv
from pathlib import Path

from oref import BusinessException, ProcessContext, Skill, SystemException


class LoadExpressions(Skill):
    """Parse the expression CSV and store rows in context."""

    def execute(self, ctx: ProcessContext) -> None:
        file_path = ctx.data.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise SystemException("Queue item payload missing file_path", action=self.name)

        path = Path(file_path)

        try:
            f = path.open("r", newline="", encoding="utf-8")
        except FileNotFoundError:
            raise SystemException(f"CSV file not found: {file_path}", action=self.name)
        except OSError as exc:
            raise SystemException(f"Unable to open CSV file {file_path}: {exc}", action=self.name) from exc

        expressions: list[dict] = []

        with f:
            reader = csv.DictReader(f)

            required = {"expression", "expected_result"}
            actual = set(reader.fieldnames) if reader.fieldnames else set()
            if not required.issubset(actual):
                missing = required - actual
                ctx.data["validation_failed"] = True
                raise BusinessException(
                    f"Missing required columns: {missing}",
                    action=self.name,
                )

            for row_num, row in enumerate(reader, start=2):
                expression = row.get("expression", "").strip()
                expected_result = row.get("expected_result", "").strip()

                if not expression:
                    continue

                expressions.append(
                    {
                        "expression": expression,
                        "expected_result": expected_result,
                        "row": row_num,
                    }
                )

        if not expressions:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                "CSV file contains no valid expressions",
                action=self.name,
            )

        ctx.data["report_file"] = str(path)
        ctx.data["expressions"] = expressions
