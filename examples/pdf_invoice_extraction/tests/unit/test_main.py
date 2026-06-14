"""Unit tests for main.py configuration and validation."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from rpacore import SystemException

from main import _validate_config, ensure_sample_data

class TestValidateConfig:
    """Tests for config validation in main.py."""

    def test_validate_config_valid(self, tmp_env: str):
        """Test that valid config passes validation."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "output_csv": "results/output.csv",
            "max_pages": 100,
            "queue": {
                "db_path": "queue.db",
                "lease_timeout": 30,
                "max_retries": 0,
            },
        }
        _validate_config(config)

    def test_validate_config_missing_key(self, tmp_env: str):
        """Test that missing required key raises SystemException."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            # Missing results_dir
            "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 0},
        }
        with pytest.raises(SystemException, match="Missing required config key"):
            _validate_config(config)

    def test_validate_config_wrong_type(self, tmp_env: str):
        """Test that wrong type raises SystemException."""
        config = {
            "max_retries": "two",  # Should be int
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 0},
        }
        with pytest.raises(SystemException, match="must be int"):
            _validate_config(config)

    def test_validate_config_negative_retries(self, tmp_env: str):
        """Test that negative max_retries raises SystemException."""
        config = {
            "max_retries": -1,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "output_csv": "results/output.csv",
            "max_pages": 100,
            "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 0},
        }
        with pytest.raises(SystemException, match="must be >= 0"):
            _validate_config(config)

    def test_validate_config_missing_queue_section(self, tmp_env: str):
        """Test that missing [queue] section raises SystemException."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "output_csv": "results/output.csv",
            "max_pages": 100,
        }
        with pytest.raises(SystemException, match="queue"):
            _validate_config(config)


class TestMainRuntime:
    def test_ensure_sample_data_generates_for_fresh_checkout(self, tmp_path, monkeypatch):
        """A fresh clone should get demo PDFs before scanning."""
        import main

        calls = []
        sample_data_dir = tmp_path / "sample_data"

        monkeypatch.setitem(
            __import__("sys").modules,
            "generate_sample_data",
            SimpleNamespace(generate_sample_data=lambda path: calls.append(path)),
        )

        ensure_sample_data({"sample_data_dir": str(sample_data_dir)})

        assert calls == [str(sample_data_dir)]

    def test_ensure_sample_data_keeps_existing_inputs(self, tmp_path, monkeypatch):
        """Existing root-level PDFs are user input and must not be regenerated."""
        import main

        calls = []
        sample_data_dir = tmp_path / "sample_data"
        sample_data_dir.mkdir()
        (sample_data_dir / "invoice.pdf").write_text("input", encoding="utf-8")

        monkeypatch.setitem(
            __import__("sys").modules,
            "generate_sample_data",
            SimpleNamespace(generate_sample_data=lambda path: calls.append(path)),
        )

        ensure_sample_data({"sample_data_dir": str(sample_data_dir)})

        assert calls == []

    def test_ensure_sample_data_keeps_processed_samples(self, tmp_path, monkeypatch):
        """A completed demo run should not regenerate duplicate invoices."""
        calls = []
        sample_data_dir = tmp_path / "sample_data"
        done_dir = sample_data_dir / "done"
        done_dir.mkdir(parents=True)
        (done_dir / "invoice.pdf").write_text("processed", encoding="utf-8")

        monkeypatch.setitem(
            __import__("sys").modules,
            "generate_sample_data",
            SimpleNamespace(generate_sample_data=lambda path: calls.append(path)),
        )

        ensure_sample_data({"sample_data_dir": str(sample_data_dir)})

        assert calls == []

    def test_main_drains_existing_queue_when_scan_adds_no_new_items(self, tmp_path, monkeypatch):
        """A zero scan count can mean all active PDFs were already queued."""
        import main

        calls = []

        monkeypatch.setattr(
            main,
            "load_config",
            lambda _: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": str(tmp_path / "rpacore.db"),
                "sample_data_dir": str(tmp_path / "sample_data"),
                "results_dir": str(tmp_path / "results"),
                "output_csv": str(tmp_path / "results" / "output.csv"),
                "max_pages": 100,
                "queue": {
                    "db_path": str(tmp_path / "queue.db"),
                    "lease_timeout": 30,
                    "max_retries": 0,
                },
            },
        )
        monkeypatch.setattr(main, "ensure_sample_data", lambda config: None)
        monkeypatch.setattr(main, "scan_inbox", lambda config, queue: 0)

        def fake_run_queue_loop(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(processed=1, completed=1, failed=0)

        monkeypatch.setattr(main, "run_queue_loop", fake_run_queue_loop)

        main.main()

        assert len(calls) == 1
        assert calls[0]["transaction_db_path"] == str(tmp_path / "rpacore.db")
