from __future__ import annotations

from datetime import datetime, timezone


def parse_git_datetime(value: str) -> datetime:
    value = value.strip()
    if len(value) >= 5 and value[-5] in ("+", "-") and value[-3] != ":":
        value = f"{value[:-2]}:{value[-2:]}"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
