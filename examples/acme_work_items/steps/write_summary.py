from __future__ import annotations

import json
from pathlib import Path

from rpacore import ProcessContext, Step, SystemException, atomic_output_path


class WriteSummary(Step):
    """Atomically write the bounded run outcome report."""

    def execute(self, ctx: ProcessContext) -> None:
        run_id = ctx.require_state("run_id", str, action=self.name)
        records = ctx.require_state("records", list, action=self.name)
        omitted = ctx.require_state("omitted_record_count", int, action=self.name)
        queue_summary = ctx.require_state("queue_summary", dict, action=self.name)
        report_dir = Path(ctx.require_config("report_dir", str, action=self.name))
        report_dir.mkdir(parents=True, exist_ok=True)
        destination = report_dir / f"summary-{run_id}.json"
        payload = {
            "run_id": run_id,
            "record_count": len(records),
            "omitted_record_count": omitted,
            "queue_summary": queue_summary,
            "records": records,
        }
        try:
            with atomic_output_path(destination) as temporary:
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(payload, stream, indent=2, ensure_ascii=False)
                    stream.write("\n")
        except (OSError, TypeError, ValueError) as exc:
            raise SystemException("Unable to write ACME summary report", action=self.name) from exc

        ctx.state["summary_path"] = str(destination)
        ctx.add_artifact(
            "acme-run-summary",
            str(destination),
            kind="report",
            metadata={"run_id": run_id, "record_count": len(records), "omitted": omitted},
        )
