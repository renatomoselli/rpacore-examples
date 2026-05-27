from __future__ import annotations

from oref import ProcessContext, Transaction


def make_context(data: dict | None = None, config: dict | None = None) -> ProcessContext:
    return ProcessContext(
        transaction=Transaction(reference="test", skills=[]),
        config=config or {},
        data=data or {},
    )
