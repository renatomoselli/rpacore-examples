from __future__ import annotations

"""Steps for the JSON Event Log Processor."""

# Shared constants used across multiple steps.
# Severity mapping derived from ALLOWED_EVENT_TYPES to avoid duplication [Q9].
ALLOWED_EVENT_TYPES = ("info", "warning", "error")
SEVERITY_MAP = {"info": "INFO", "warning": "WARNING", "error": "ERROR"}

if set(ALLOWED_EVENT_TYPES) != set(SEVERITY_MAP):
    raise ValueError(
        "ALLOWED_EVENT_TYPES and SEVERITY_MAP must have the same keys",
    )
