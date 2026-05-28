"""Unit tests for main.py configuration and validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from oref import SystemException

from main import _validate_config


class TestValidateConfig:
    """Tests for config validation in main.py."""

    def test_validate_config_valid(self, tmp_env: str):
        """Test that valid config passes validation."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "db_path": "queue.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "output_csv": "results/output.csv",
            "max_pages": 100,
        }
        # Should not raise
        _validate_config(config)

    def test_validate_config_missing_key(self, tmp_env: str):
        """Test that missing required key raises SystemException."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "db_path": "queue.db",
            "sample_data_dir": "sample_data",
            # Missing results_dir
        }
        with pytest.raises(SystemException, match="Missing required config key"):
            _validate_config(config)

    def test_validate_config_wrong_type(self, tmp_env: str):
        """Test that wrong type raises SystemException."""
        config = {
            "max_retries": "two",  # Should be int
            "log_level": "INFO",
            "db_path": "queue.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
        }
        with pytest.raises(SystemException, match="must be int"):
            _validate_config(config)

    def test_validate_config_negative_retries(self, tmp_env: str):
        """Test that negative max_retries raises SystemException."""
        config = {
            "max_retries": -1,
            "log_level": "INFO",
            "db_path": "queue.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "output_csv": "results/output.csv",
            "max_pages": 100,
        }
        with pytest.raises(SystemException, match="must be >= 0"):
            _validate_config(config)
