from __future__ import annotations

from pathlib import Path

from rpacore import (
    Engine,
    HistoryEntry,
    ProcessContext,
    resume_transaction,
    save_transaction,
    resolve_config_paths,
    Status,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
)

from skills.save_state import SaveState
from skills.fail_task import FailTask

logger = get_logger(__name__)

# The project root is the directory containing main.py.
PROJECT_ROOT = Path(__file__).resolve().parent


def _create_skills() -> list[SaveState | FailTask]:
    return [
        SaveState(name="save_state", execution_order=1),
        FailTask(name="fail_task", execution_order=2),
    ]


def _log_history(history: list[HistoryEntry]) -> None:
    for entry in history:
        logger.info(
            "  %s - %s (order %s)",
            entry.event.value,
            entry.skill_name,
            entry.skill_execution_order,
        )


def _save_transaction(tx: Transaction, db_path: str, *, checkpoint_path: str | None = None) -> None:
    try:
        save_transaction(tx, db_path=db_path)
    except Exception:
        if checkpoint_path is not None:
            Path(checkpoint_path).unlink(missing_ok=True)
        raise


def main() -> None:
    # Load and validate config
    config = load_config(str(PROJECT_ROOT / "config.toml"))
    config = resolve_config_paths(
        config,
        ["transaction_db_path", "checkpoint_path"],
        base_dir=PROJECT_ROOT,
        root=PROJECT_ROOT,
    )
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=config["max_retries"])
    db_path = config["transaction_db_path"]

    # --- First run ---
    logger.info("=== Starting first run ===")
    tx = Transaction(
        reference="checkpoint-resume-demo",
        state={},
        metadata={"example": "checkpoint_resume"},
        skills=_create_skills(),
    )
    engine.run(
        ProcessContext(transaction=tx, config=config),
        checkpoint=lambda transaction: _save_transaction(
            transaction,
            db_path,
            checkpoint_path=config["checkpoint_path"],
        ),
    )

    logger.info("First run status: %s", tx.status)
    _log_history(tx.history)

    # --- Resume if not successful ---
    final_tx = tx
    if tx.status != Status.SUCCESSFUL:
        logger.info("Resuming transaction...")
        # Toggle fail_on_first_run to False for resume
        resume_config = dict(config)
        resume_config["fail_on_first_run"] = False

        resumed_tx = resume_transaction(
            tx_id=tx.id,
            skills=_create_skills(),
            db_path=db_path,
        )
        # Keep the existing checkpoint artifact if resume persistence fails; it
        # still represents the successful pre-resume state.
        engine.run(
            ProcessContext(transaction=resumed_tx, config=resume_config),
            checkpoint=lambda transaction: _save_transaction(transaction, db_path),
        )
        final_tx = resumed_tx

        logger.info("Resume status: %s", resumed_tx.status)
        _log_history(resumed_tx.history)

    # --- Summary ---
    logger.info("Final state: counter=%s", final_tx.state.get("counter", {}))
    logger.info("Resume complete: %s", final_tx.state.get("resume_complete"))
    logger.info("=== Checkpoint/resume demo complete ===")


if __name__ == "__main__":
    main()
