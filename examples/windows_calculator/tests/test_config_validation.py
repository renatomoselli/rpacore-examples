"""Unit tests for Windows Calculator config validation."""

from __future__ import annotations

import pytest

from rpacore import SystemException

from main import _validate_config


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
