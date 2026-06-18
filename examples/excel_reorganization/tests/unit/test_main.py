from __future__ import annotations

import pytest
from rpacore import Status, SystemException

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

    main._validate_config(config)

    assert config["csv_path"] == str(project_root / "sample.csv")
    assert config["output_dir"] == str(project_root / "output")
    assert config["transaction_db_path"] == str(project_root / "rpacore.db")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"max_retries": "2"}, "must be int"),
        ({"log_level": "TRACE"}, "log_level"),
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

    with pytest.raises(SystemException, match="must resolve under"):
        main._validate_config(config)


def test_main_does_not_persist_failed_transaction_and_cleans_output(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    output_path = project_root / "output" / "failed.xlsx"
    output_path.parent.mkdir()
    output_path.write_text("partial", encoding="utf-8")

    class FailedEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, ctx):
            ctx.transaction.status = Status.FAILED
            ctx.transaction.state["output_path"] = str(output_path)

    def fail_if_saved(*_args, **_kwargs):
        raise AssertionError("failed transactions should not be saved")

    monkeypatch.setattr(main, "load_config", lambda _path: config)
    monkeypatch.setattr(main, "Engine", FailedEngine)
    monkeypatch.setattr(main, "save_transaction", fail_if_saved)

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    assert not output_path.exists()


def test_main_raises_system_exception_when_successful_transaction_cannot_persist(tmp_path, monkeypatch):
    project_root, config = _valid_config(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
    output_path = project_root / "output" / "orphaned.xlsx"
    output_path.parent.mkdir()
    output_path.write_text("generated", encoding="utf-8")

    class SuccessfulEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, ctx):
            ctx.transaction.status = Status.SUCCESSFUL
            ctx.transaction.state["output_path"] = str(output_path)

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(main, "load_config", lambda _path: config)
    monkeypatch.setattr(main, "Engine", SuccessfulEngine)
    monkeypatch.setattr(main, "save_transaction", fail_save)

    with pytest.raises(SystemException, match="Failed to persist transaction"):
        main.main()

    assert not output_path.exists()


def test_cleanup_failed_output_removes_state_output_path(tmp_path):
    output_path = tmp_path / "failed.xlsx"
    output_path.write_text("generated", encoding="utf-8")
    tx = main.Transaction(reference="cleanup", state={"output_path": str(output_path)})

    main._cleanup_failed_output(tx, main.logger)

    assert not output_path.exists()
