from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rpacore import Engine, ProcessContext, Transaction


@pytest.fixture
def sample_checkpoint_path(tmp_path: Path) -> Path:
    return tmp_path / "checkpoint.json"


@pytest.fixture
def sample_db_path(tmp_path: Path) -> Path:
    return tmp_path / "rpacore.db"


@pytest.fixture
def run_step():
    def _run_step(step: Any, state: dict | None = None, config: dict | None = None) -> Transaction:
        tx = Transaction(
            reference=f"test-{step.name}",
            state=state or {},
            steps=[step],
        )
        Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config or {}))
        return tx

    return _run_step
