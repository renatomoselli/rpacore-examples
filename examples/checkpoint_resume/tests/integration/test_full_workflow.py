from __future__ import annotations

from pathlib import Path

import pytest

from rpacore import (
    Engine,
    ProcessContext,
    Status,
    save_transaction,
    resume_transaction,
    Transaction,
    load_transaction,
)

from skills.save_state import SaveState
from skills.fail_task import FailTask
from main import DEFINITION_IDENTITY


def _build_config(db_path: str, checkpoint_path: str, fail_on_first_run: bool) -> dict:
    """Build a minimal config dict for testing."""
    return {
        "max_retries": 0,
        "log_level": "WARNING",
        "transaction_db_path": db_path,
        "checkpoint_path": checkpoint_path,
        "fail_on_first_run": fail_on_first_run,
    }


def _create_skills():
    """Return the skill list used by this example."""
    return [
        SaveState(name="save_state", execution_order=1),
        FailTask(name="fail_task", execution_order=2),
    ]


def _run_first_run(db_path: str, checkpoint_path: str, fail_on_first_run: bool = True):
    """Run the transaction once (first run). Returns (tx, config)."""
    config = _build_config(
        db_path,
        checkpoint_path,
        fail_on_first_run=fail_on_first_run,
    )
    tx = Transaction(
        reference="checkpoint-resume-demo",
        definition_identity=DEFINITION_IDENTITY,
        state={},
        metadata={"example": "checkpoint_resume"},
        skills=_create_skills(),
    )
    Engine(max_retries=0).run(
        ProcessContext(transaction=tx, config=config),
        checkpoint=lambda transaction: save_transaction(transaction, db_path=db_path),
    )
    return tx, config


def _resume_and_run(
    db_path: str,
    checkpoint_path: str,
    tx_id: str,
    fail_on_first_run: bool = False,
):
    """Load, resume, and run a transaction. Returns (resumed_tx, config)."""
    config = _build_config(
        db_path,
        checkpoint_path,
        fail_on_first_run=fail_on_first_run,
    )
    persisted_tx = load_transaction(tx_id, db_path=db_path)
    resumed_tx = resume_transaction(
        tx_id=persisted_tx.id,
        skills=_create_skills(),
        db_path=db_path,
        definition_identity=DEFINITION_IDENTITY,
    )
    Engine(max_retries=0).run(
        ProcessContext(transaction=resumed_tx, config=config),
        checkpoint=lambda transaction: save_transaction(transaction, db_path=db_path),
    )
    return resumed_tx, config


class TestFullWorkflow:
    """Integration tests for the full checkpoint/resume workflow."""

    def test_first_run_fails_second_run_succeeds(self, tmp_path: Path) -> None:
        """Simulate the full first-run + resume workflow."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=True)

        # First run should have failed
        assert tx.status == Status.FAILED
        # But save_state should have succeeded and set counter
        assert "counter" in tx.state
        assert tx.state["counter"]["value"] == 1

        # Resume
        resumed_tx, _ = _resume_and_run(
            db_path, checkpoint_path, tx.id, fail_on_first_run=False
        )

        # Resume should succeed
        assert resumed_tx.status == Status.SUCCESSFUL
        assert resumed_tx.state["counter"]["value"] == 2
        assert resumed_tx.state["resume_complete"] is True

    def test_resume_skips_successful_skill(self, tmp_path: Path) -> None:
        """Verify that save_state is not re-executed on resume."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=True)
        first_counter = tx.state["counter"]["value"]

        # Resume
        resumed_tx, _ = _resume_and_run(
            db_path, checkpoint_path, tx.id, fail_on_first_run=False
        )

        # Counter should only have been incremented by FailTask (not SaveState again)
        assert resumed_tx.state["counter"]["value"] == first_counter + 1

    def test_history_contains_resume_event(self, tmp_path: Path) -> None:
        """Verify that the TRANSACTION_RESUMED event is in history."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=True)

        # Resume
        resumed_tx, _ = _resume_and_run(
            db_path, checkpoint_path, tx.id, fail_on_first_run=False
        )

        events = [entry.event.value for entry in resumed_tx.history]
        assert "transaction_resumed" in events

    def test_happy_path_no_resume_needed(self, tmp_path: Path) -> None:
        """When fail_on_first_run is False from the start, transaction succeeds without resume."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=False)

        assert tx.status == Status.SUCCESSFUL
        # SaveState increments counter to 1, FailTask increments to 2
        assert tx.state["counter"]["value"] == 2
        assert tx.state["resume_complete"] is True

    def test_resume_preserves_successful_skill_state(self, tmp_path: Path) -> None:
        """Verify that save_state counter is preserved across resume."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=True)
        first_counter = tx.state["counter"]["value"]

        # Resume
        resumed_tx, _ = _resume_and_run(
            db_path, checkpoint_path, tx.id, fail_on_first_run=False
        )

        assert resumed_tx.state["counter"]["value"] == first_counter + 1

    def test_resume_with_no_prior_db_entry_raises(self, tmp_path: Path) -> None:
        """Resuming a non-existent transaction should fail."""
        db_path = str(tmp_path / "rpacore.db")
        with pytest.raises(KeyError):
            resume_transaction(
                tx_id="non-existent-id",
                skills=_create_skills(),
                db_path=db_path,
                definition_identity=DEFINITION_IDENTITY,
            )

    def test_resume_can_fail_again_when_recovered_state_is_invalid(self, tmp_path: Path) -> None:
        """Document that resume can still fail if durable state is corrupted."""
        db_path = str(tmp_path / "rpacore.db")
        checkpoint_path = str(tmp_path / "checkpoint.json")
        tx, _ = _run_first_run(db_path, checkpoint_path, fail_on_first_run=True)
        tx.state.pop("counter")
        save_transaction(tx, db_path=db_path)

        resumed_tx, _ = _resume_and_run(
            db_path,
            checkpoint_path,
            tx.id,
            fail_on_first_run=False,
        )

        assert resumed_tx.status == Status.FAILED
        assert "counter" in str(resumed_tx.failed_skills()[0].exceptions[-1]).lower()
