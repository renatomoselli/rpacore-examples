from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class WriteOutput(Skill):
    """Write normalized events as JSONL to the results folder."""

    def execute(self, ctx: ProcessContext) -> None:
        normalized_events = ctx.require_state("normalized_events", list, action=self.name)
        current_file = ctx.require_state("current_file", str, action=self.name)
        results_dir = ctx.require_state("results_dir", str, action=self.name)

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
            fd, tmp_path = tempfile.mkstemp(
                dir=results_resolved, suffix=".tmp", prefix=f"{stem}_cleaned_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    for event in normalized_events:
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")
                os.replace(tmp_path, str(output_resolved))

                ctx.add_artifact(
                    name=f"{stem}_cleaned.jsonl",
                    path=str(output_resolved),
                    kind="output",
                    metadata={
                        "source_file": str(current_file),
                        "event_count": len(normalized_events),
                    },
                )
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

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
