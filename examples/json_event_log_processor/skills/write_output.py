from __future__ import annotations

import json
import os
import tempfile
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

        # Build output filename: events_001.json -> events_001_cleaned.jsonl
        stem = Path(current_file).stem
        output_file = Path(results_dir) / f"{stem}_cleaned.jsonl"

        # Trust-boundary check: output path must resolve under results_dir [S2]
        results_resolved = Path(results_dir).resolve()
        output_resolved = output_file.resolve()
        if not output_resolved.is_relative_to(results_resolved):
            raise SystemException(
                f"Output path escapes results directory: {output_file}",
                action=self.name,
            )

        try:
            # Atomic write: write to a temp file in the same directory, then
            # os.replace() so readers never see a partial file.  [Q6]
            fd, tmp_path = tempfile.mkstemp(
                dir=results_resolved,
                suffix=".tmp",
                prefix=f"{stem}_cleaned_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    for event in normalized_events:
                        f.write(json.dumps(event, ensure_ascii=False) + "\n")
                os.replace(tmp_path, str(output_resolved))
            except BaseException:
                # Clean up temp file on any failure (including KeyboardInterrupt)
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
