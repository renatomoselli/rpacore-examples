"""RPA Core skill: load test expressions from a CSV file."""
from __future__ import annotations

import csv

from rpacore import BusinessException, ProcessContext, Skill, SystemException

from skills._path_utils import validate_contained_path


class LoadExpressions(Skill):
    """Parse the expression CSV and store rows in context."""

    def execute(self, ctx: ProcessContext) -> None:
        file_path = ctx.require_state("file_path", str, action=self.name)
        input_dir = ctx.require_config("input_dir", str, action=self.name)
        path = validate_contained_path(file_path, input_dir, action=self.name)

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
                ctx.state["validation_failed"] = True
                raise BusinessException(
                    f"Missing required columns: {missing}",
                    action=self.name,
                    stop=True,
                )

            for row_num, row in enumerate(reader, start=2):
                expression = (row.get("expression") or "").strip()
                expected_result = (row.get("expected_result") or "").strip()

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
            ctx.state["validation_failed"] = True
            raise BusinessException(
                "CSV file contains no valid expressions",
                action=self.name,
                stop=True,
            )

        ctx.state["report_file"] = str(path)
        ctx.state["expressions"] = expressions
