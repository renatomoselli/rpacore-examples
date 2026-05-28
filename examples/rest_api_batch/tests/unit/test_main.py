"""Unit tests for main.py config validation."""

import pytest

from oref import SystemException


class TestValidateConfig:
    """Test the _validate_config function."""

    def test_passes_for_valid_config(self):
        """Test that valid config passes validation."""
        from main import _validate_config

        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "db_path": "oref.db",
            "output_file": "output.jsonl",
        }
        _validate_config(config)  # Should not raise

    def test_raises_on_missing_key(self):
        """Test that missing config key raises SystemException."""
        from main import _validate_config

        config = {
            "max_retries": 2,
            "log_level": "INFO",
            # missing db_path and output_file
        }

        with pytest.raises(SystemException) as exc_info:
            _validate_config(config)

        assert "Missing required config key" in str(exc_info.value)

    def test_raises_on_wrong_type(self):
        """Test that wrong config value type raises SystemException."""
        from main import _validate_config

        config = {
            "max_retries": "not_an_int",  # should be int
            "log_level": "INFO",
            "db_path": "oref.db",
            "output_file": "output.jsonl",
        }

        with pytest.raises(SystemException) as exc_info:
            _validate_config(config)

        assert "must be int" in str(exc_info.value)

    def test_raises_on_negative_max_retries(self):
        """Test that negative max_retries raises SystemException."""
        from main import _validate_config

        config = {
            "max_retries": -1,
            "log_level": "INFO",
            "db_path": "oref.db",
            "output_file": "output.jsonl",
        }

        with pytest.raises(SystemException) as exc_info:
            _validate_config(config)

        assert "must be >= 0" in str(exc_info.value)

    def test_zero_max_retries_is_valid(self):
        """Test that zero max_retries is accepted."""
        from main import _validate_config

        config = {
            "max_retries": 0,
            "log_level": "INFO",
            "db_path": "oref.db",
            "output_file": "output.jsonl",
        }
        _validate_config(config)  # Should not raise
