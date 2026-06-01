from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

from rpacore import (
    BusinessException,
    ProcessContext,
    Skill,
    SystemException,
    get_logger,
    list_transactions,
)

logger = get_logger(__name__)


class WriteErrorReport(Skill):
    """Read failed transactions from SQLite and write a JSON error report."""

    def execute(self, ctx: ProcessContext) -> None:
        db_path = ctx.config["db_path"]
        results_dir = ctx.config["results_dir"]

        try:
            transactions = list_transactions(db_path)
        except (sqlite3.Error, OSError) as exc:
            raise SystemException(
                f"Failed to read transactions from database {db_path}: {exc}",
                action=self.name,
            ) from exc

        failed_txs = [
            tx for tx in transactions
            if tx.status.name != "SUCCESSFUL"
        ]

        report = {
            "total_transactions": len(transactions),
            "successful": sum(1 for tx in transactions if tx.status.name == "SUCCESSFUL"),
            "failed": len(failed_txs),
            "failures": [],
        }

        for tx in failed_txs:
            tx_entry = {
                "transaction_id": tx.id,
                "transaction_reference": tx.reference,
                "status": tx.status.name,
                "retry_count": tx.retry_count,
                "failed_skills": [],
            }

            for skill in tx.ordered_skills():
                if skill.exceptions:
                    for exc in skill.exceptions:
                        tx_entry["failed_skills"].append({
                            "skill_name": skill.name,
                            "skill_order": skill.execution_order,
                            "exception_type": "business" if isinstance(exc, BusinessException) else "system",
                            "message": str(exc),
                        })

            report["failures"].append(tx_entry)

        try:
            Path(results_dir).mkdir(parents=True, exist_ok=True)
            report_path = Path(results_dir) / "error_report.json"

            # Trust-boundary check: output path must resolve under results_dir [S2]
            results_resolved = Path(results_dir).resolve()
            report_resolved = report_path.resolve()
            if not report_resolved.is_relative_to(results_resolved):
                raise SystemException(
                    f"Report path escapes results directory: {report_path}",
                    action=self.name,
                )

            # Atomic write [Q6]
            fd, tmp_path = tempfile.mkstemp(
                dir=results_resolved,
                suffix=".tmp",
                prefix="error_report_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, default=str)
                os.replace(tmp_path, str(report_resolved))
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info("Wrote error report to %s", report_path)
        except OSError as exc:
            raise SystemException(
                f"Failed to write error report to {report_path}: {exc}",
                action=self.name,
            ) from exc
