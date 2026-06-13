"""RPA Core skill: close the Calculator application (best-effort cleanup)."""
from __future__ import annotations

import logging

from rpacore import ProcessContext, Skill

logger = logging.getLogger(__name__)


class CloseCalculator(Skill):
    """Close the Calculator app. Always succeeds — best-effort cleanup."""

    def execute(self, ctx: ProcessContext) -> None:
        interactor = ctx.resources.get("interactor")
        if interactor is None:
            logger.warning("No interactor to close")
            return

        interactor.close()
