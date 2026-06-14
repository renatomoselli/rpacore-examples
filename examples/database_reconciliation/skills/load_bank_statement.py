from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from rpacore import ProcessContext, Skill, SystemException

from skills._csv_utils import read_csv

REQUIRED_COLUMNS = ("posted_date", "reference", "amount", "description")


class LoadBankStatement(Skill):
    """Load bank statement entries from CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        csv_path = ctx.require_config("bank_statement_csv", str, action=self.name)
        if not csv_path:
            raise SystemException(
                "Config key 'bank_statement_csv' must be a non-empty string",
                action=self.name,
            )

        rows = read_csv(Path(csv_path), REQUIRED_COLUMNS, self.name)
        by_reference: dict[str, list[dict[str, object]]] = {}

        for index, row in enumerate(rows, start=2):
            missing = [
                column
                for column in REQUIRED_COLUMNS
                if not str(row.get(column, "")).strip()
            ]
            if missing:
                raise SystemException(
                    f"Bank statement row {index} missing required column(s): {', '.join(missing)}",
                    action=self.name,
                )
            try:
                amount = Decimal(row["amount"])
            except InvalidOperation as exc:
                raise SystemException(
                    f"Bank statement row {index} has invalid amount: {row['amount']!r}",
                    action=self.name,
                ) from exc

            entry = {
                "posted_date": row["posted_date"],
                "reference": row["reference"],
                "amount": str(amount),
                "description": row["description"],
            }
            by_reference.setdefault(row["reference"], []).append(entry)

        ctx.state["bank_by_reference"] = by_reference
