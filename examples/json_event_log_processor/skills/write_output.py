from __future__ import annotations

import json
from pathlib import Path

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class WriteOutput(Skill):
    """Write normalized events as JSONL to the results folder."""

    def execute(self, ctx: ProcessContext) -> None:
        normalized_events = ctx.data.get("normalized_events")
        if normalized_events is None:
            raise SystemException(
                "No normalized_events in context — normalize_events must run first",
                action=self.name,
            )

        current_file = ctx.data.get("current_file")
        results_dir = ctx.data.get("results_dir")

        if current_file is None or results_dir is None:
            raise SystemException(
                "Missing current_file or results_dir in context",
                action=self.name,
            )

        # Build output filename: events_001.json → events_001_cleaned.jsonl
        stem = Path(current_file).stem
        output_file = str(Path(results_dir) / f"{stem}_cleaned.jsonl")

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                for event in normalized_events:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            logger.info(
                "Wrote %d normalized events to %s",
                len(normalized_events),
                output_file,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write to output file {output_file}: {exc}",
                action=self.name,
            ) from exc
