"""Unit tests for JSON Event Log Processor config validation."""

from __future__ import annotations

import pytest

from rpacore import SystemException

from main import _validate_config


def _valid_config() -> dict:
    return {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "rpacore.db",
        "inbox_dir": "inbox",
        "results_dir": "results",
    }


def test_validate_config_accepts_valid_config():
    config = _valid_config()

    _validate_config(config)

    assert config["transaction_db_path"].endswith("rpacore.db")
    assert config["inbox_dir"].endswith("inbox")
    assert config["results_dir"].endswith("results")


def test_validate_config_rejects_old_db_path_key():
    config = _valid_config()
    config["db_path"] = config.pop("transaction_db_path")

    with pytest.raises(SystemException) as exc_info:
        _validate_config(config)

    assert "transaction_db_path" in str(exc_info.value)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("max_retries", True, "int"),
        ("log_level", 123, "str"),
        ("transaction_db_path", 123, "str"),
    ],
)
def test_validate_config_rejects_wrong_types(key, value, message):
    config = _valid_config()
    config[key] = value

    with pytest.raises(SystemException) as exc_info:
        _validate_config(config)

    assert message in str(exc_info.value)


@pytest.mark.parametrize("max_retries", [-1, 11])
def test_validate_config_rejects_retry_bounds(max_retries):
    config = _valid_config()
    config["max_retries"] = max_retries

    with pytest.raises(SystemException):
        _validate_config(config)


def test_validate_config_rejects_invalid_log_level():
    config = _valid_config()
    config["log_level"] = "TRACE"

    with pytest.raises(SystemException) as exc_info:
        _validate_config(config)

    assert "log_level" in str(exc_info.value)


def test_validate_config_rejects_path_escape():
    config = _valid_config()
    config["inbox_dir"] = "../outside"

    with pytest.raises(SystemException):
        _validate_config(config)
