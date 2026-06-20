"""Shared currency parsing helpers for invoice skills."""

from __future__ import annotations

import re

CURRENCY_TOKEN_PATTERN = r"(?:USD|EUR|GBP|JPY|BRL|R\$|R|[$€£¥]|â‚¬|Â£|Â¥)"
CURRENCY_AFFIX_RE = re.compile(
    rf"^{CURRENCY_TOKEN_PATTERN}\s*|\s*{CURRENCY_TOKEN_PATTERN}$",
    re.IGNORECASE,
)


def try_parse_currency_number(value: object) -> float | None:
    """Parse a number with a supported currency prefix or suffix."""
    cleaned = str(value).replace(",", "").strip()
    cleaned = CURRENCY_AFFIX_RE.sub("", cleaned).strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None
