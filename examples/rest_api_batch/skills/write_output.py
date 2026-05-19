from __future__ import annotations

import json

from oref import ProcessContext, Skill, SystemException, get_logger

logger = get_logger(__name__)


class WriteOutput(Skill):
    """Append an enriched record to the JSONL output file."""

    def execute(self, ctx: ProcessContext) -> None:
        record = ctx.data.get("enriched_record")
        if record is None:
            raise SystemException(
                "No enriched_record in context — enrich_record must run first",
                action=self.name,
            )

        output_file = str(ctx.config.get("output_file", "output.jsonl"))

        try:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(
                "Wrote record for post %s to %s",
                record.get("postId"),
                output_file,
            )
        except OSError as exc:
            raise SystemException(
                f"Failed to write to output file {output_file}: {exc}",
                action=self.name,
            ) from exc
