from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from rpacore import ProcessContext, Skill, get_logger

logger = get_logger(__name__)


class SaveState(Skill):
    """SaveState records durable state and succeeds.

    Reads or initializes a counter from ctx.state, increments it,
    writes the counter to a JSON checkpoint file, and records an artifact.
    """

    def execute(self, ctx: ProcessContext) -> None:
        # 1. Read or initialize counter from state
        counter_data = ctx.optional_state(
            "counter", dict, default={}, action=self.name
        )
        current_value = counter_data.get("value", 0)

        # 2. Increment and write the checkpoint artifact before mutating state.
        new_value = current_value + 1
        now = datetime.now(timezone.utc).isoformat()
        counter_data = {"value": new_value, "timestamp": now}
        checkpoint_path = Path(
            ctx.require_config("checkpoint_path", str, action=self.name)
        )
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=checkpoint_path.parent,
                delete=False,
            ) as f:
                temp_path = f.name
                json.dump(counter_data, f, indent=2)
            os.replace(temp_path, checkpoint_path)
        finally:
            if temp_path is not None and Path(temp_path).exists():
                Path(temp_path).unlink()
        logger.info("SaveState: wrote checkpoint to %s", checkpoint_path)

        ctx.state["counter"] = counter_data
        logger.info("SaveState: counter set to %d", new_value)

        ctx.add_artifact(
            name="checkpoint",
            path=str(checkpoint_path),
            kind="json",
            metadata={"counter": new_value},
        )

        logger.info("SaveState: completed successfully")
