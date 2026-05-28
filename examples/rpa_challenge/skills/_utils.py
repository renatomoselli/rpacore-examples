"""Shared utilities for RPA Challenge skills."""

from __future__ import annotations


# Default timeouts (milliseconds) — overridable via config.toml
DEFAULT_TIMEOUTS = {
    "page_load": 30_000,
    "click": 10_000,
    "form_transition": 10_000,
    "congratulations_check": 5_000,
    "score_extraction": 15_000,
}


def get_timeout(config: dict, key: str) -> int:
    """Read a timeout value from config, falling back to default.

    Args:
        config: The application config dict.
        key: Timeout key (e.g. ``"click"``, ``"form_transition"``).

    Returns:
        Timeout in milliseconds.
    """
    return int(config.get(f"timeout_{key}", DEFAULT_TIMEOUTS[key]))


def find_row_value(row: dict, field: str) -> str:
    """Look up a field value case-insensitively.

    Handles mismatched casing between Excel headers and the expected field names
    (e.g. ``"first name"`` vs ``"First Name"``).

    Args:
        row: A dictionary representing one row of the input spreadsheet.
        field: The canonical field name to look up (e.g. ``"Email"``).

    Returns:
        The matched value as a string, or ``""`` if not found or empty.
    """
    lower = field.lower()
    for key, val in row.items():
        if str(key).strip().lower() == lower:
            return str(val) if val else ""
    return ""
