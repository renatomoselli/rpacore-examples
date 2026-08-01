from __future__ import annotations

from pathlib import Path

from rpacore import (
    ConfigField,
    Engine,
    HistoryEvent,
    HistoryEntry,
    ProcessContext,
    SystemException,
    atomic_output_path,
    generate_report,
    resume_transaction,
    save_transaction,
    resolve_config_paths,
    Status,
    Transaction,
    configure_logger,
    get_logger,
    load_config,
    validate_config,
)

from skills.save_state import SaveState
from skills.fail_task import FailTask

logger = get_logger(__name__)
DEFINITION_IDENTITY = "checkpoint-resume/v1"

# The project root is the directory containing main.py.
PROJECT_ROOT = Path(__file__).resolve().parent
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_CONFIG_FIELDS = (
    ConfigField("max_retries", int, min_value=0),
    ConfigField("log_level", str, choices=_LOG_LEVELS),
    ConfigField("transaction_db_path", str, allow_empty=False),
    ConfigField("checkpoint_path", str, allow_empty=False),
    ConfigField("fail_on_first_run", bool),
)


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


def _load_example_config(path: Path | None = None) -> dict[str, object]:
    config_path = path or PROJECT_ROOT / "config.toml"
    config = load_config(config_path, require_file=True)
    try:
        validate_config(config, _CONFIG_FIELDS)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemException(f"Invalid config: {exc}", action="main") from exc
    for key in ("transaction_db_path", "checkpoint_path"):
        if not str(config[key]).strip():
            raise SystemException(f"{key} must be a non-empty path", action="main")
    resolved = resolve_config_paths(
        config,
        ("transaction_db_path", "checkpoint_path"),
        base_dir=config_path.resolve().parent,
        root=PROJECT_ROOT,
    )
    resolved["report_dir"] = str((PROJECT_ROOT / "reports").resolve())
    return resolved


def _is_save_state_success_checkpoint(tx: Transaction) -> bool:
    if not tx.history:
        return False
    event = tx.history[-1]
    return (
        event.event is HistoryEvent.SKILL_SUCCEEDED
        and event.skill_name == "save_state"
        and event.skill_execution_order == 1
    )


def _save_transaction(tx: Transaction, db_path: str, *, checkpoint_path: str | None = None) -> None:
    try:
        save_transaction(tx, db_path=db_path)
    except Exception:
        if checkpoint_path is not None and _is_save_state_success_checkpoint(tx):
            Path(checkpoint_path).unlink(missing_ok=True)
        raise


def _publish_report_record(tx: Transaction, report_dir: str, *, phase: str) -> Path:
    report = generate_report(tx)
    if report.record is None:
        raise SystemException("Unable to create canonical transaction report record", action="report")
    destination = Path(report_dir) / f"{tx.id}.{phase}.report-v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output_path(destination) as temporary:
        temporary.write_text(report.record.payload_json, encoding="utf-8")
    return destination


def main() -> None:
    config = _load_example_config()
    configure_logger(level=str(config["log_level"]))

    engine = Engine(max_retries=int(config["max_retries"]))
    db_path = str(config["transaction_db_path"])

    # --- First run ---
    logger.info("=== Starting first run ===")
    tx = Transaction(
        reference="checkpoint-resume-demo",
        definition_identity=DEFINITION_IDENTITY,
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
        save_transaction(tx, db_path=db_path)
        _publish_report_record(tx, str(config["report_dir"]), phase="failed")
        logger.info("Resuming transaction...")
        # Toggle fail_on_first_run to False for resume
        resume_config = dict(config)
        resume_config["fail_on_first_run"] = False

        resumed_tx = resume_transaction(
            tx_id=tx.id,
            skills=_create_skills(),
            db_path=db_path,
            definition_identity=DEFINITION_IDENTITY,
        )
        # Keep the existing checkpoint artifact if resume persistence fails; it
        # still represents the successful pre-resume state.
        engine.run(
            ProcessContext(transaction=resumed_tx, config=resume_config),
            checkpoint=lambda transaction: _save_transaction(transaction, db_path),
        )
        final_tx = resumed_tx
        save_transaction(resumed_tx, db_path=db_path)
        _publish_report_record(resumed_tx, str(config["report_dir"]), phase="resumed")

        logger.info("Resume status: %s", resumed_tx.status)
        _log_history(resumed_tx.history)

    # --- Summary ---
    logger.info("Final state: counter=%s", final_tx.state.get("counter", {}))
    logger.info("Resume complete: %s", final_tx.state.get("resume_complete"))
    logger.info("=== Checkpoint/resume demo complete ===")


if __name__ == "__main__":
    main()
