"""Pytest fixtures for Git Repository Health Monitor tests."""

from __future__ import annotations

import sys
from pathlib import Path

from rpacore import ProcessContext, Transaction

sys.path.insert(0, str(Path(__file__).parent.parent))


def make_context(state: dict | None = None, config: dict | None = None) -> ProcessContext:
    """Build a ProcessContext for unit testing with real Transaction objects."""
    tx = Transaction(reference="test", skills=[], state=state or {})
    return ProcessContext(transaction=tx, config=config or {})
