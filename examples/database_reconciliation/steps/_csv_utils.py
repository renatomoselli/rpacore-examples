from __future__ import annotations

import csv
from pathlib import Path

from rpacore import SystemException


def read_csv(path: Path, required_columns: tuple[str, ...], action: str) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise SystemException(f"CSV file has no header: {path}", action=action)
            missing_headers = [column for column in required_columns if column not in reader.fieldnames]
            if missing_headers:
                raise SystemException(
                    f"CSV file {path} missing required header(s): {', '.join(missing_headers)}",
                    action=action,
                )
            return list(reader)
    except OSError as exc:
        raise SystemException(f"Unable to read CSV file {path}: {exc}", action=action) from exc
