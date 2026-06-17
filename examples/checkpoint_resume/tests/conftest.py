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
def run_skill():
    def _run_skill(skill: Any, state: dict | None = None, config: dict | None = None) -> Transaction:
        tx = Transaction(
            reference=f"test-{skill.name}",
            state=state or {},
            skills=[skill],
        )
        Engine(max_retries=0).run(ProcessContext(transaction=tx, config=config or {}))
        return tx

    return _run_skill
