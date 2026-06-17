from __future__ import annotations

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class FailTask(Skill):
    """FailTask simulates interruption or raises a controlled system failure.

    - Reads `fail_on_first_run` from config
    - If fail_on_first_run is True, raises SystemException("Simulated failure on first run")
    - If False, reads ctx.state["counter"] and increments it, writes back
    - On success, sets ctx.state["resume_complete"] = True
    """

    def execute(self, ctx: ProcessContext) -> None:
        fail_on_first_run = ctx.require_config(
            "fail_on_first_run", bool, action=self.name
        )

        if fail_on_first_run:
            logger.warning("FailTask: fail_on_first_run is True — raising SystemException")
            raise SystemException(
                "Simulated failure on first run",
                action=self.name,
            )

        # On resume (fail_on_first_run is False), work with the counter
        if "counter" not in ctx.state:
            raise SystemException(
                "counter state is required before fail_task runs; check skill execution_order",
                action=self.name,
            )

        counter_data = ctx.require_state(
            "counter", dict, action=self.name
        )
        current_value = counter_data.get("value", 0)
        updated_counter = {**counter_data, "value": current_value + 1}
        ctx.state["counter"] = updated_counter
        ctx.state["resume_complete"] = True
        logger.info("FailTask: counter incremented to %d, resume_complete set", updated_counter["value"])
