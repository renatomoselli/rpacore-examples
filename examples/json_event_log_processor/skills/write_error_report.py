from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from oref import (
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
        db_path = str(ctx.config.get("db_path", "oref.db"))
        results_dir = str(ctx.config.get("results_dir", "results"))

        try:
            transactions = list_transactions(db_path, limit=1000)
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
            report_path = str(Path(results_dir) / "error_report.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Wrote error report to %s", report_path)
        except OSError as exc:
            raise SystemException(
                f"Failed to write error report to {report_path}: {exc}",
                action=self.name,
            ) from exc
