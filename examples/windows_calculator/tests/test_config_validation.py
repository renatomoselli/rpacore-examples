"""Unit tests for Windows Calculator config validation."""

from __future__ import annotations

import pytest

from rpacore import SystemException

import main
from main import _load_example_config, _validate_config


def _valid_config() -> dict:
    return {
        "engine_max_retries": 1,
        "log_level": "INFO",
        "transaction_db_path": "rpacore.db",
        "input_dir": "input",
        "output_dir": "output",
        "done_dir": "done",
        "failed_dir": "failed",
        "calculator_path": "calculator.exe",
        "queue": {
            "db_path": "queue.db",
            "lease_timeout": 30,
            "max_retries": 0,
        },
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("engine_max_retries", True),
        ("log_level", 123),
        ("transaction_db_path", 123),
    ],
)
def test_validate_config_rejects_wrong_top_level_types(key, value):
    config = _valid_config()
    config[key] = value

    with pytest.raises(SystemException):
        _validate_config(config)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("db_path", True),
        ("lease_timeout", True),
        ("max_retries", False),
    ],
)
def test_validate_config_rejects_bool_queue_values(key, value):
    config = _valid_config()
    config["queue"][key] = value

    with pytest.raises(SystemException):
        _validate_config(config)


def test_validate_config_rejects_queue_retry_before_failed_file_disposition():
    config = _valid_config()
    config["queue"]["max_retries"] = 1

    with pytest.raises(SystemException, match="queue.max_retries"):
        _validate_config(config)


def test_validate_config_wraps_missing_queue_path_as_system_exception():
    config = _valid_config()
    del config["queue"]["db_path"]

    with pytest.raises(SystemException, match="Missing required config key: queue.db_path"):
        _validate_config(config)


def test_validate_config_rejects_lowercase_log_level():
    config = _valid_config()
    config["log_level"] = "info"

    with pytest.raises(SystemException, match="log_level"):
        _validate_config(config)


@pytest.mark.parametrize(
    "key",
    (
        "input_dir",
        "output_dir",
        "done_dir",
        "failed_dir",
        "transaction_db_path",
        "queue.db_path",
    ),
)
def test_load_example_config_rejects_paths_outside_project(tmp_path, monkeypatch, key):
    config = _valid_config()
    if key == "queue.db_path":
        config["queue"]["db_path"] = "../outside/value"
    else:
        config[key] = "../outside/value"
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda _, *, require_file: config)

    with pytest.raises(SystemException, match="resolves outside root"):
        _load_example_config()


def test_load_example_config_is_rooted_and_allows_external_calculator_path(tmp_path, monkeypatch):
    external_calculator = tmp_path.parent / "Calculator.exe"
    config = _valid_config()
    config.update(
        {
            "input_dir": "input",
            "output_dir": "output",
            "done_dir": "done",
            "failed_dir": "failed",
            "transaction_db_path": "state/rpacore.db",
            "calculator_path": str(external_calculator),
        }
    )
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda _, *, require_file: config)

    loaded = _load_example_config()

    assert config["input_dir"] == "input"
    assert config["queue"]["db_path"] == "queue.db"
    assert loaded["input_dir"] == str(tmp_path / "input")
    assert loaded["queue"]["db_path"] == str(tmp_path / "queue.db")
    assert loaded["calculator_path"] == str(external_calculator.resolve())


def test_load_example_config_requires_root_config_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

    with pytest.raises(FileNotFoundError, match="Config file not found"):
        _load_example_config()
