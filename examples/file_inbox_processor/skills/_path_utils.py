"""Shared path validation utilities for file-handling skills."""

from __future__ import annotations

from pathlib import Path

from rpacore import SystemException


def validate_contained_path(file_path: str, allowed_base: str, action: str) -> Path:
    """Resolve *file_path* and verify it lives under *allowed_base*.

    Returns the resolved :class:`Path` if valid, otherwise raises
    :class:`SystemException`.

    Callers typically guard this with an ``inbox_dir`` presence check so
    that isolated unit tests (which omit full config) skip validation
    gracefully.  Production always supplies ``inbox_dir`` via
    ``_validate_config()``.
    """
    resolved = Path(file_path).resolve()
    base = Path(allowed_base).resolve()
    if not resolved.is_relative_to(base):
        raise SystemException(
            f"File path outside allowed directory: {file_path}",
            action=action,
        )
    return resolved
