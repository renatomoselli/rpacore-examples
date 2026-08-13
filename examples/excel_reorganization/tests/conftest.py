from __future__ import annotations

from rpacore import ProcessContext, Transaction


def make_context(state: dict | None = None, config: dict | None = None) -> ProcessContext:
    tx = Transaction(reference="test", steps=[], state=state or {})
    return ProcessContext(
        transaction=tx,
        config=config or {},
    )
