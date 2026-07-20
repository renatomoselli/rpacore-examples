from __future__ import annotations

import pytest
from rpacore import (
    BusinessException,
    OutcomeCategory,
    RetryDisposition,
    Skill,
    Status,
    SystemException,
    list_transactions,
    load_transaction,
)

import main


def _valid_config(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "sample.csv").write_text("employee_name,date,amount,country\n", encoding="utf-8")
    return project_root, {
        "max_retries": 0,
        "log_level": "INFO",
        "csv_path": "sample.csv",
        "output_dir": "output",
        "transaction_db_path": "rpacore.db",
    }


def test_validate_config_resolves_paths_under_project_root(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)

    validated = main._validate_config(config)

    assert config["csv_path"] == "sample.csv"
    assert config["output_dir"] == "output"
    assert config["transaction_db_path"] == "rpacore.db"
    assert validated == {
        "max_retries": 0,
        "log_level": "INFO",
        "csv_path": str(project_root / "sample.csv"),
        "output_dir": str(project_root / "output"),
        "transaction_db_path": str(project_root / "rpacore.db"),
    }
    assert validated is not config


def test_validate_config_retains_optional_output_filename(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    config["output_filename"] = "custom_{month}.xlsx"

    validated = main._validate_config(config)

    assert validated["output_filename"] == "custom_{month}.xlsx"


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"max_retries": "2"}, "expected int"),
        ({"log_level": "TRACE"}, "log_level"),
        ({"max_retries": -1}, ">= 0"),
        ({"csv_path": ""}, "non-empty"),
    ],
)
def test_validate_config_rejects_invalid_values(tmp_path, monkeypatch, update, match):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    config.update(update)

    with pytest.raises(SystemException, match=match):
        main._validate_config(config)


def test_validate_config_rejects_missing_key(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    del config["csv_path"]

    with pytest.raises(SystemException, match="Missing required config key: csv_path"):
        main._validate_config(config)


def test_validate_config_rejects_legacy_db_path(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    del config["transaction_db_path"]
    config["db_path"] = "legacy.db"

    with pytest.raises(SystemException, match="db_path"):
        main._validate_config(config)


def test_validate_config_rejects_path_traversal(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    config["csv_path"] = "../outside.csv"

    with pytest.raises(SystemException, match="resolves outside root"):
        main._validate_config(config)


def test_main_loads_required_project_root_config_from_nested_directory(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    nested_directory = project_root / "nested" / "launch"
    nested_directory.mkdir(parents=True)
    calls = []

    def fake_load_config(path, *, require_file):
        calls.append((path, require_file))
        return config

    def successful_execution(tx, **_kwargs):
        tx.status = Status.SUCCESSFUL

    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(main, "load_config", fake_load_config)
    monkeypatch.setattr(main, "execute_transaction", successful_execution)
    monkeypatch.chdir(nested_directory)

    main.main()

    assert calls == [(project_root / "config.toml", True)]


def test_main_persists_failed_transaction_and_cleans_output(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    output_path = project_root / "output" / "failed.xlsx"
    output_path.parent.mkdir()
    output_path.write_text("partial", encoding="utf-8")

    class FailedLoad(Skill):
        def execute(self, ctx):
            ctx.transaction.state["output_path"] = str(output_path)
            raise BusinessException("expected failure", action=self.name, stop=True)

    monkeypatch.setattr(main, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(main, "LoadSalesData", FailedLoad)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    assert not output_path.exists()
    persisted = load_transaction(
        next(iter(list_transactions(db_path=str(project_root / "rpacore.db")))).id,
        db_path=str(project_root / "rpacore.db"),
    )
    assert persisted.status is Status.FAILED
    assert persisted.outcome_category is OutcomeCategory.BUSINESS_FAILED
    assert persisted.retry_disposition is RetryDisposition.NOT_REQUESTED


def test_main_raises_system_exception_when_checkpoint_fails_after_output(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    output_path = project_root / "output" / "orphaned.xlsx"
    output_path.parent.mkdir()
    output_path.write_text("generated", encoding="utf-8")

    def fail_checkpoint(tx, **_kwargs):
        tx.state["output_path"] = str(output_path)
        raise OSError("disk full")

    monkeypatch.setattr(main, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(main, "execute_transaction", fail_checkpoint)

    with pytest.raises(SystemException, match="Failed to execute and checkpoint transaction"):
        main.main()

    assert not output_path.exists()


def test_main_uses_strict_execution_helper_without_a_final_save(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    calls = []

    def successful_execution(tx, **kwargs):
        calls.append(kwargs)
        tx.status = Status.SUCCESSFUL

    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(main, "load_config", lambda *_args, **_kwargs: config)
    monkeypatch.setattr(main, "execute_transaction", successful_execution)

    main.main()

    assert len(calls) == 1
    assert calls[0]["transaction_db_path"] == str(project_root / "rpacore.db")
    assert isinstance(calls[0]["engine"], main.Engine)
    assert not hasattr(main, "save_transaction")


def test_cleanup_failed_output_removes_state_output_path(tmp_path):
    output_path = tmp_path / "failed.xlsx"
    output_path.write_text("generated", encoding="utf-8")
    tx = main.Transaction(reference="cleanup", state={"output_path": str(output_path)})

    main._cleanup_failed_output(tx, main.logger)

    assert not output_path.exists()
