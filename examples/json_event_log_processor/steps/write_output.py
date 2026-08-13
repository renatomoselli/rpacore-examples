from __future__ import annotations
import json
from pathlib import Path

from rpacore import ProcessContext, Step, SystemException, atomic_output_path, get_logger

logger = get_logger(__name__)


class WriteOutput(Step):
    """Write normalized events as JSONL to the results folder."""

    def execute(self, ctx: ProcessContext) -> None:
        normalized_events = ctx.require_state("normalized_events", list, action=self.name)
        current_file = ctx.require_state("current_file", str, action=self.name)
        results_dir = ctx.require_config("results_dir", str, action=self.name)

        stem = Path(current_file).stem
        output_file = Path(results_dir) / f"{stem}_cleaned.jsonl"

        results_resolved = Path(results_dir).resolve()
        output_resolved = output_file.resolve()
        if not output_resolved.is_relative_to(results_resolved):
            raise SystemException(
                f"Output path escapes results dir: {output_file}",
                action=self.name,
            )

        try:
            with atomic_output_path(output_resolved) as temporary:
                with temporary.open("w", encoding="utf-8") as f:
                    for event in normalized_events:
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")

            ctx.add_artifact(
                name=f"{stem}_cleaned.jsonl",
                path=str(output_resolved),
                kind="output",
                metadata={
                    "source_file": str(current_file),
                    "event_count": len(normalized_events),
                },
            )

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
