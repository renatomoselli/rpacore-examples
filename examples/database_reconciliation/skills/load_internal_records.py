from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from oref import ProcessContext, Skill, SystemException

REQUIRED_COLUMNS = ("payment_id", "date", "reference", "amount", "vendor")


class LoadInternalRecords(Skill):
    """Load ERP/accounting payment records from CSV."""

    def execute(self, ctx: ProcessContext) -> None:
        csv_path = ctx.config.get("internal_records_csv")
        if not isinstance(csv_path, str) or not csv_path:
            raise SystemException(
                "Config key 'internal_records_csv' must be a non-empty string",
                action=self.name,
            )

        rows = _read_csv(Path(csv_path), self.name)
        records = []
        for index, row in enumerate(rows, start=2):
            missing = [column for column in REQUIRED_COLUMNS if not row.get(column)]
            if missing:
                raise SystemException(
                    f"Internal record row {index} missing required column(s): {', '.join(missing)}",
                    action=self.name,
                )
            try:
                amount = Decimal(row["amount"])
            except InvalidOperation as exc:
                raise SystemException(
                    f"Internal record row {index} has invalid amount: {row['amount']!r}",
                    action=self.name,
                ) from exc

            records.append(
                {
                    "payment_id": row["payment_id"],
                    "date": row["date"],
                    "reference": row["reference"],
                    "amount": amount,
                    "vendor": row["vendor"],
                }
            )

        ctx.data["internal_records"] = records


def _read_csv(path: Path, action: str) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise SystemException(f"CSV file has no header: {path}", action=action)
            missing_headers = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
            if missing_headers:
                raise SystemException(
                    f"CSV file {path} missing required header(s): {', '.join(missing_headers)}",
                    action=action,
                )
            return list(reader)
    except OSError as exc:
        raise SystemException(f"Unable to read CSV file {path}: {exc}", action=action) from exc
