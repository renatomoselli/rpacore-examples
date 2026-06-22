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
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Engine retries are sequential; concurrent writers are outside this example's contract.
            existing_content, already_written = _read_output(
                output_path,
                record,
                action=self.name,
            )
            if already_written:
                logger.info(
                    "Record for post %s already exists in %s; skipping duplicate write",
                    record.get("postId"),
                    output_path,
                )
                _add_output_artifact(
                    ctx,
                    output_path,
                    record,
                    deduplicated=True,
                )
                return

            if existing_content and not existing_content.endswith("\n"):
                existing_content += "\n"
            new_content = (
                existing_content
                + json.dumps(record, ensure_ascii=False)
                + "\n"
            )
            fd, tmp_path = tempfile.mkstemp(
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp_path), str(output_path))
            tmp_path = None
            logger.info(
                "Wrote record for post %s to %s",
                record.get("postId"),
                output_path,
            )
            _add_output_artifact(
                ctx,
                output_path,
                record,
                deduplicated=False,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write to output file {output_path}: {exc}",
                action=self.name,
            ) from exc
        finally:
            # Clean up temp file if replace failed
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as exc:
                    logger.warning("Could not remove temporary output %s: %s", tmp_path, exc)


def _read_output(
    output_path: Path,
    record: dict,
    *,
    action: str = "write_output",
) -> tuple[str, bool]:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return "", False

    content = output_path.read_text(encoding="utf-8")
    target_post_id = record.get("postId")
    for line_number, line in enumerate(
        content.splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            existing = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemException(
                f"Output file {output_path} contains invalid JSON on line {line_number}",
                action=action,
            ) from exc
        if not isinstance(existing, dict):
            raise SystemException(
                f"Output file {output_path} contains a non-object on line {line_number}",
                action=action,
            )
        if target_post_id is not None and existing.get("postId") == target_post_id:
            return content, True
        if target_post_id is None and existing == record:
            return content, True
    return content, False


def _add_output_artifact(
    ctx: ProcessContext,
    output_path: Path,
    record: dict,
    *,
    deduplicated: bool,
) -> None:
    ctx.add_artifact(
        name="output-jsonl",
        path=str(output_path),
        kind="jsonl",
        metadata={
            "example": "rest_api_batch",
            "post_id": record.get("postId"),
            "deduplicated": deduplicated,
        },
    )
