"""Configuration tests for the File Inbox Processor entry point."""

from __future__ import annotations

from copy import deepcopy

import pytest

import main as file_inbox_main
from rpacore import SystemException


def _valid_config() -> dict[str, object]:
    return {
        "max_retries": 1,
        "log_level": "INFO",
        "log_format": "json",
        "transaction_db_path": "state/rpacore.db",
        "inbox_dir": "inbox",
        "done_dir": "done",
        "failed_dir": "failed",
        "master_csv": "output/master.csv",
        "queue": {
            "db_path": "state/queue.db",
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }


def test_validate_config_resolves_all_configured_paths_without_mutating_input(tmp_path, monkeypatch):
    config = _valid_config()
    config["extra_setting"] = {"keep": True}
    original = deepcopy(config)
    monkeypatch.setattr(file_inbox_main, "PROJECT_ROOT", tmp_path)

    validated = file_inbox_main._validate_config(config)

    assert config == original
    assert validated["transaction_db_path"] == str(tmp_path / "state" / "rpacore.db")
    assert validated["inbox_dir"] == str(tmp_path / "inbox")
    assert validated["done_dir"] == str(tmp_path / "done")
    assert validated["failed_dir"] == str(tmp_path / "failed")
    assert validated["master_csv"] == str(tmp_path / "output" / "master.csv")
    assert validated["queue"] == {
        "db_path": str(tmp_path / "state" / "queue.db"),
        "lease_timeout": 30,
        "max_retries": 0,
    }
    assert "queue.db_path" not in validated
    assert validated["extra_setting"] == {"keep": True}


@pytest.mark.parametrize(
    ("update", "match"),
    [
        (lambda config: config.__setitem__("max_retries", -1), "max_retries"),
        (lambda config: config.__setitem__("max_retries", True), "max_retries"),
        (lambda config: config.__setitem__("log_level", "TRACE"), "log_level"),
        (lambda config: config.__setitem__("log_format", "yaml"), "log_format"),
        (lambda config: config.__setitem__("transaction_db_path", ""), "transaction_db_path"),
        (lambda config: config["queue"].__setitem__("db_path", ""), "queue.db_path"),  # type: ignore[index,union-attr]
        (lambda config: config["queue"].__setitem__("lease_timeout", 0), "queue.lease_timeout"),  # type: ignore[index,union-attr]
        (lambda config: config["queue"].__setitem__("max_retries", -1), "queue.max_retries"),  # type: ignore[index,union-attr]
    ],
)
def test_validate_config_rejects_invalid_scalar_and_queue_values(tmp_path, monkeypatch, update, match):
    config = _valid_config()
    monkeypatch.setattr(file_inbox_main, "PROJECT_ROOT", tmp_path)
    update(config)

    with pytest.raises(SystemException, match=match):
        file_inbox_main._validate_config(config)


@pytest.mark.parametrize(
    ("remove", "match"),
    [
        (lambda config: config.pop("inbox_dir"), "inbox_dir"),
        (lambda config: config.pop("queue"), "queue.db_path"),
        (lambda config: config["queue"].pop("lease_timeout"), "queue.lease_timeout"),  # type: ignore[index,union-attr]
    ],
)
def test_validate_config_rejects_missing_required_values(tmp_path, monkeypatch, remove, match):
    config = _valid_config()
    monkeypatch.setattr(file_inbox_main, "PROJECT_ROOT", tmp_path)
    remove(config)

    with pytest.raises(SystemException, match=match):
        file_inbox_main._validate_config(config)


@pytest.mark.parametrize(
    "path_key",
    (
        "transaction_db_path",
        "inbox_dir",
        "done_dir",
        "failed_dir",
        "master_csv",
        "queue.db_path",
    ),
)
def test_validate_config_rejects_each_path_escape(tmp_path, monkeypatch, path_key):
    config = _valid_config()
    monkeypatch.setattr(file_inbox_main, "PROJECT_ROOT", tmp_path)
    if path_key == "queue.db_path":
        config["queue"]["db_path"] = "../outside.db"  # type: ignore[index]
    else:
        config[path_key] = "../outside"  # type: ignore[index]

    with pytest.raises(SystemException, match="resolves outside root"):
        file_inbox_main._validate_config(config)


def test_load_example_config_uses_required_project_root_file(tmp_path, monkeypatch):
    observed: dict[str, object] = {}
    monkeypatch.setattr(file_inbox_main, "PROJECT_ROOT", tmp_path)

    def fake_load_config(path, *, require_file):
        observed["path"] = path
        observed["require_file"] = require_file
        return _valid_config()

    monkeypatch.setattr(file_inbox_main, "load_config", fake_load_config)

    config = file_inbox_main._load_example_config()

    assert observed == {"path": tmp_path / "config.toml", "require_file": True}
    assert config["inbox_dir"] == str(tmp_path / "inbox")
