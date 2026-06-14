from __future__ import annotations

from rpacore import SystemException

"""Shared utilities for RPA Challenge skills."""


# Default timeouts (milliseconds) — overridable via config.toml
DEFAULT_TIMEOUTS = {
    "page_load": 30_000,
    "click": 10_000,
    "form_transition": 10_000,
    "congratulations_check": 5_000,
    "score_extraction": 15_000,
}

REQUIRED_FIELDS = [
    "First Name",
    "Last Name",
    "Company Name",
    "Role in Company",
    "Address",
    "Email",
    "Phone Number",
]


def get_timeout(config: dict, key: str) -> int:
    """Read a timeout value from config, falling back to default.

    Args:
        config: The application config dict.
        key: Timeout key (e.g. ``"click"``, ``"form_transition"``).

    Returns:
        Timeout in milliseconds.
    """
    default = DEFAULT_TIMEOUTS.get(key)
    if default is None:
        raise KeyError(f"Unknown timeout key: {key}")
    config_key = f"timeout_{key}"
    raw_value = config.get(config_key, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SystemException(
            f"Config key '{config_key}' must be an integer, got {raw_value!r}",
            action="config",
        ) from exc


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
            return str(val) if val is not None else ""
    return ""


def missing_required_fields(row: dict, fields: list[str] | None = None) -> list[str]:
    """Return required field names that are missing or blank in a row."""
    required = REQUIRED_FIELDS if fields is None else fields
    return [field for field in required if not find_row_value(row, field).strip()]
