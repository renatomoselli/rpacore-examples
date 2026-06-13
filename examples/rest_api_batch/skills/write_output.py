from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class WriteOutput(Skill):
    """Append an enriched record to the JSONL output file."""

    def execute(self, ctx: ProcessContext) -> None:
        record = ctx.require_state("enriched_record", dict, action=self.name)

        output_path = Path(ctx.require_config("output_file", str, action=self.name))
        tmp_path = None

        try:
            if _record_already_written(output_path, record):
                logger.info(
                    "Record for post %s already exists in %s; skipping duplicate write",
                    record.get("postId"),
                    output_path,
                )
                ctx.add_artifact(
                    name="output-jsonl",
                    path=str(output_path),
                    kind="jsonl",
                    metadata={
                        "example": "rest_api_batch",
                        "post_id": record.get("postId"),
                        "deduplicated": True,
                    },
                )
                return

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
            ctx.add_artifact(
                name="output-jsonl",
                path=str(output_path),
                kind="jsonl",
                metadata={
                    "example": "rest_api_batch",
                    "post_id": record.get("postId"),
                },
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


def _record_already_written(output_path: Path, record: dict) -> bool:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False

    target_post_id = record.get("postId")
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            existing = json.loads(line)
        except json.JSONDecodeError:
            continue
        if target_post_id is not None and existing.get("postId") == target_post_id:
            return True
        if target_post_id is None and existing == record:
            return True
    return False
