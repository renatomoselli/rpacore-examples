from __future__ import annotations

import json
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class LoadJsonFile(Skill):
    """Read and parse a JSON event log file from the inbox folder."""

    def execute(self, ctx: ProcessContext) -> None:
        current_file = ctx.require_state("current_file", str, action=self.name)
        if current_file is None:
            raise SystemException(
                "No current_file in context — main.py must set it first",
                action=self.name,
            )

        # Trust-boundary check: resolved path must stay under inbox_dir [S2]
        inbox_dir = ctx.require_config("inbox_dir", str, action=self.name)
        resolved = Path(current_file).resolve()
        if not resolved.is_relative_to(Path(inbox_dir).resolve()):
            raise SystemException(
                f"File escapes inbox directory: {current_file}",
                action=self.name,
            )

        try:
            with open(current_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError as exc:
            raise SystemException(
                f"File not found: {current_file}",
                action=self.name,
                code="json_event_log.input.missing_file",
            ) from exc
        except json.JSONDecodeError as exc:
            raise SystemException(
                f"Malformed JSON in {current_file}: {exc}",
                action=self.name,
                code="json_event_log.input.malformed_json",
            ) from exc
        except OSError as exc:
            raise SystemException(
                f"Failed to read file {current_file}: {exc}",
                action=self.name,
                code="json_event_log.input.read_failed",
            ) from exc

        # Support both single event object and array of events.
        # Non-dict list items are intentionally accepted here; ValidateEvents
        # handles schema validation downstream.  [Q11]
        if isinstance(data, dict):
            events = [data]
        elif isinstance(data, list):
            events = data
        else:
            raise SystemException(
                f"Expected JSON object or array in {current_file}, got {type(data).__name__}",
                action=self.name,
            )

        ctx.state["events"] = events
        ctx.transaction.metadata["event_count"] = len(events)
        logger.info(
            "Loaded %d events from %s",
            len(events),
            current_file,
        )
