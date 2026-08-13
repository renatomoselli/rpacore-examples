"""Shared path helpers for the Windows Calculator workflow."""
from __future__ import annotations

from pathlib import Path

from rpacore import SystemException


def validate_contained_path(file_path: str, allowed_base: str, *, action: str) -> Path:
    """Resolve a path and require it to remain under the allowed directory."""
    resolved = Path(file_path).resolve()
    base = Path(allowed_base).resolve()
    if not resolved.is_relative_to(base):
        raise SystemException(
            f"File path outside allowed directory: {file_path}",
            action=action,
        )
    return resolved


def unique_destination(directory: Path, filename: str, *, action: str) -> Path:
    """Return a non-existing destination, preserving the original suffix."""
    destination = directory / filename
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate

    raise SystemException(
        f"Unable to find available destination for {filename}",
        action=action,
    )
