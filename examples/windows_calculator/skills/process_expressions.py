"""RPA Core skill: type each expression into Calculator and compare results."""
from __future__ import annotations

import logging

from rpacore import ProcessContext, Skill, Status, SystemException

logger = logging.getLogger(__name__)


class ProcessExpressions(Skill):
    """Iterate expressions, type each one, read and compare the result."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return

        interactor = ctx.resources.get("interactor")
        if interactor is None:
            raise SystemException("No interactor in context", action=self.name)

        expressions = ctx.require_state("expressions", list, action=self.name)
        if not expressions:
            raise SystemException("No expressions in context", action=self.name)

        results: list[dict[str, object]] = []

        for idx, expr_data in enumerate(expressions):
            expression = expr_data["expression"]
            expected = expr_data["expected_result"]

            try:
                interactor.type_expression(expression)
                actual = interactor.get_result()
            except Exception as exc:
                logger.error("Expression %d: %s", idx + 1, exc)
                results.append(
                    {
                        "expression": expression,
                        "expected_result": expected,
                        "actual": None,
                        "passed": False,
                    }
                )
                continue

            passed = actual == expected
            results.append(
                {
                    "expression": expression,
                    "expected_result": expected,
                    "actual": actual,
                    "passed": passed,
                }
            )

            if not passed:
                logger.error(
                    "Expression %d: FAIL — expected '%s', got '%s'", idx + 1, expected, actual
                )

        ctx.state["results"] = results
        ctx.state["has_failures"] = any(not bool(result["passed"]) for result in results)
