"""Unit tests for main.py config validation."""

import json

import pytest

from rpacore import Skill, SystemException


class TestValidateConfig:
    """Test the _validate_config function."""

    def test_passes_for_valid_config(self):
        """Test that valid config passes validation."""
        from main import _validate_config

        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
        }
        _validate_config(config)  # Should not raise

    def test_raises_on_missing_key(self):
        """Test that missing config key raises SystemException."""
        from main import _validate_config

        config = {
            "max_retries": 2,
            "log_level": "INFO",
            # missing transaction_db_path and output_file
            "api_mode": "fixture",
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
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
        }

        with pytest.raises(SystemException) as exc_info:
            _validate_config(config)

        assert "must be int" in str(exc_info.value)

    def test_rejects_bool_as_int(self):
        """Test that bool (which is subclass of int) is rejected by strict type check."""
        from main import _validate_config

        config = {
            "max_retries": True,  # bool is subclass of int, must be rejected
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
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
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
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
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
        }
        _validate_config(config)  # Should not raise

    def test_raises_on_invalid_api_mode(self):
        """Test that api_mode must be fixture or live."""
        from main import _validate_config

        config = {
            "max_retries": 0,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "internet",
        }

        with pytest.raises(SystemException) as exc_info:
            _validate_config(config)

        assert "api_mode" in str(exc_info.value)


class TestMainRuntime:
    def test_main_preserves_existing_output_when_setup_fails(self, tmp_path, monkeypatch):
        """Test that failed setup does not erase the previous successful output."""
        import main

        class FailingFetchPosts(Skill):
            def execute(self, ctx):
                raise SystemException("setup failed", action=self.name)

        existing = json.dumps({"postId": 999}) + "\n"
        output_file = tmp_path / "output.jsonl"
        output_file.write_text(existing, encoding="utf-8")

        monkeypatch.setattr(main, "FetchPosts", FailingFetchPosts)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": str(tmp_path / "rpacore.db"),
                "output_file": str(output_file),
                "api_mode": "fixture",
            },
        )

        with pytest.raises(SystemExit):
            main.main()

        assert output_file.read_text(encoding="utf-8") == existing

    def test_main_replaces_existing_output_file(self, tmp_path, monkeypatch):
        """Test that a rerun starts with a clean output file."""
        import main

        output_file = tmp_path / "output.jsonl"
        output_file.write_text(json.dumps({"postId": 999}) + "\n", encoding="utf-8")

        monkeypatch.setattr(
            main,
            "load_config",
            lambda _: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": str(tmp_path / "rpacore.db"),
                "output_file": str(output_file),
                "api_mode": "fixture",
            },
        )

        main.main()

        post_ids = [
            json.loads(line)["postId"]
            for line in output_file.read_text(encoding="utf-8").splitlines()
        ]
        assert post_ids == [1, 3]
