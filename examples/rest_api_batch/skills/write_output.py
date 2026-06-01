from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger
from skills import KEY_ENRICHED_RECORD

logger = get_logger(__name__)


class WriteOutput(Skill):
    """Append an enriched record to the JSONL output file."""

    def execute(self, ctx: ProcessContext) -> None:
        record = ctx.data.get(KEY_ENRICHED_RECORD)
        if record is None:
            raise SystemException(
                "No enriched_record in context — enrich_record must run first",
                action=self.name,
            )

        output_path = Path(ctx.config.get("output_file", "output.jsonl"))
        tmp_path = None

        try:
            if not output_path.exists() or output_path.stat().st_size == 0:
                # First write — create via atomic temp-file + replace
                fd, tmp_path = tempfile.mkstemp(
                    dir=output_path.parent, suffix=".tmp"
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                os.replace(str(tmp_path), str(output_path))
                tmp_path = None
            else:
                # Subsequent writes — append
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(
                "Wrote record for post %s to %s",
                record.get("postId"),
                output_path,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write to output file {output_path}: {exc}",
                action=self.name,
            ) from exc
        finally:
            # Clean up temp file if replace failed
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
