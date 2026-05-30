"""Skills for the JSON Event Log Processor."""

# Shared constants used across multiple skills.
# Severity mapping derived from ALLOWED_EVENT_TYPES to avoid duplication [Q9].
ALLOWED_EVENT_TYPES = ("info", "warning", "error")
SEVERITY_MAP = {"info": "INFO", "warning": "WARNING", "error": "ERROR"}
