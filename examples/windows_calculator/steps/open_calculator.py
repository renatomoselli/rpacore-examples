"""RPA Core step: launch the Windows Calculator application."""
from __future__ import annotations

from rpacore import ProcessContext, Step, SystemException

from calculator_utils import CalculatorInteractor


class OpenCalculator(Step):
    """Launch Calculator and store the interactor in context."""

    def execute(self, ctx: ProcessContext) -> None:
        # Use existing interactor from context (e.g., test injection) or create a new one
        interactor = ctx.resources.get("interactor")
        if interactor is None:
            calculator_path = ctx.config.get("calculator_path")
            interactor = CalculatorInteractor(calculator_path=calculator_path)

            if not interactor.launch():
                raise SystemException(
                    "Failed to launch Calculator",
                    action=self.name,
                )

        ctx.resources["interactor"] = interactor
