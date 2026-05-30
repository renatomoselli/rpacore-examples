"""OREF skill: type each expression into Calculator and compare results."""
from __future__ import annotations

import logging

from oref import ProcessContext, Skill, Status, SystemException

from calculator_utils import CalculatorResult

logger = logging.getLogger(__name__)


class ProcessExpressions(Skill):
    """Iterate expressions, type each one, read and compare the result."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.data.get("validation_failed"):
            self.status = Status.SKIPPED
            return

        interactor = ctx.data.get("interactor")
        if interactor is None:
            raise SystemException("No interactor in context", action=self.name)

        expressions = ctx.data.get("expressions")
        if not isinstance(expressions, list) or not expressions:
            raise SystemException("No expressions in context", action=self.name)

        results: list[CalculatorResult] = []

        for idx, expr_data in enumerate(expressions):
            expression = expr_data["expression"]
            expected = expr_data["expected_result"]

            try:
                interactor.type_expression(expression)
                actual = interactor.get_result()
            except Exception as exc:
                logger.error("Expression %d: %s", idx + 1, exc)
                results.append(
                    CalculatorResult(expression=expression, expected=expected, actual=None, passed=False)
                )
                continue

            passed = actual == expected
            results.append(
                CalculatorResult(expression=expression, expected=expected, actual=actual, passed=passed)
            )

            if not passed:
                logger.error(
                    "Expression %d: FAIL — expected '%s', got '%s'", idx + 1, expected, actual
                )

        ctx.data["results"] = results
        ctx.data["has_failures"] = any(not result.passed for result in results)
