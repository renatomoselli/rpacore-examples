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
        db_path = ctx.require_config("transaction_db_path", str, action=self.name)
        results_dir = ctx.require_config("results_dir", str, action=self.name)
        run_id = ctx.optional_state("run_id", str, None, action=self.name)
        if run_id is None:
            config_run_id = ctx.config.get("run_id")
            if isinstance(config_run_id, str) and config_run_id:
                run_id = config_run_id
        if not run_id:
            raise SystemException(
                "Missing required run_id for scoped error report",
                action=self.name,
            )

        try:
            transactions = list_transactions(db_path)
        except (sqlite3.Error, OSError) as exc:
            raise SystemException(
                f"Failed to read transactions from db {db_path}: {exc}",
                action=self.name,
            ) from exc

        transactions = [
            tx for tx in transactions
            if tx.metadata.get("run_id") == run_id
            and tx.metadata.get("transaction_kind") != "error-report"
        ]

        successful_count = sum(1 for tx in transactions if tx.status.name == "SUCCESSFUL")
        failed_txs = [tx for tx in transactions if tx.status.name == "FAILED"]
        unresolved_count = len(transactions) - successful_count - len(failed_txs)
        persistence_errors = ctx.config.get("persistence_errors", [])
        if not isinstance(persistence_errors, list):
            persistence_errors = []
        else:
            persistence_errors = list(persistence_errors)

        report = {
            "total_transactions": len(transactions),
            "successful": successful_count,
            "failed": len(failed_txs),
            "unresolved": unresolved_count,
            "persistence_error_count": len(persistence_errors),
            "persistence_errors": persistence_errors,
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

        report_path = Path(results_dir) / "error_report.json"

        try:
            Path(results_dir).mkdir(parents=True, exist_ok=True)
            results_resolved = Path(results_dir).resolve()
            report_resolved = report_path.resolve()
            if not report_resolved.is_relative_to(results_resolved):
                raise SystemException(
                    f"Report path escapes results dir: {report_path}",
                    action=self.name,
                )

            fd, tmp_path = tempfile.mkstemp(
                dir=results_resolved, suffix=".tmp", prefix="error_report_",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, default=str)
                os.replace(tmp_path, str(report_resolved))

                ctx.add_artifact(
                    name="error_report.json",
                    path=str(report_resolved),
                    kind="report",
                    metadata={
                        "total_transactions": len(transactions),
                        "failed_count": len(failed_txs),
                        "unresolved_count": unresolved_count,
                        "persistence_error_count": len(persistence_errors),
                        "run_id": run_id,
                    },
                )
                ctx.transaction.metadata["run_id"] = run_id
                ctx.transaction.metadata["error_count"] = len(failed_txs)
                ctx.transaction.metadata["unresolved_count"] = unresolved_count
                ctx.transaction.metadata["persistence_error_count"] = len(persistence_errors)
            except Exception:
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
