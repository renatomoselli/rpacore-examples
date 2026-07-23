"""Unit tests for main.py configuration and validation."""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest

from rpacore import QueueItem, QueueRunSummary, SystemException

from main import _has_sample_pdfs, _validate_config, build_transaction, ensure_sample_data

class TestValidateConfig:
    """Tests for config validation in main.py."""

    def test_validate_config_valid(self, tmp_env: Path):
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

    def test_validate_config_missing_key(self, tmp_env: Path):
        """Test that missing required key raises SystemException."""
        config = {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            # Missing results_dir
            "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 0},
        }
        with pytest.raises(SystemException) as error:
            _validate_config(config)
        assert "results_dir" in str(error.value)

    def test_validate_config_wrong_type(self, tmp_env: Path):
        """Test that wrong type raises SystemException."""
        config = {
            "max_retries": "two",  # Should be int
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "sample_data_dir": "sample_data",
            "results_dir": "results",
            "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 0},
        }
        with pytest.raises(SystemException) as error:
            _validate_config(config)
        assert "max_retries" in str(error.value)

    def test_validate_config_negative_retries(self, tmp_env: Path):
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
        with pytest.raises(SystemException) as error:
            _validate_config(config)
        assert "max_retries" in str(error.value)

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("max_pages", 0),
            ("max_pages", -1),
            ("output_csv", ""),
        ],
    )
    def test_validate_config_rejects_invalid_output_limits(self, key, value):
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
        config[key] = value

        with pytest.raises(SystemException) as error:
            _validate_config(config)
        assert key in str(error.value)

    def test_validate_config_missing_queue_section(self, tmp_env: Path):
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
    def test_has_sample_pdfs_ignores_unprocessed_nested_folders(self, tmp_path):
        sample_data_dir = tmp_path / "sample_data"
        archive_dir = sample_data_dir / "archive"
        archive_dir.mkdir(parents=True)
        (archive_dir / "invoice.pdf").write_text("archived", encoding="utf-8")

        assert _has_sample_pdfs(str(sample_data_dir)) is False

    def test_build_transaction_requires_original_name(self):
        item = QueueItem(reference="missing-name", payload={"file_path": "invoice.pdf"})

        with pytest.raises(SystemException, match="original_name"):
            build_transaction(item)

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
        loaded_paths = []
        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

        def fake_load_config(path, *, require_file):
            assert require_file is True
            loaded_paths.append(path)
            return {
                "max_retries": 0,
                "log_level": "WARNING",
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

        monkeypatch.setattr(main, "load_config", fake_load_config)
        monkeypatch.setattr(main, "ensure_sample_data", lambda config: None)
        monkeypatch.setattr(main, "scan_inbox", lambda config, queue: 0)

        def fake_run_queue_loop(**kwargs):
            calls.append(kwargs)
            return QueueRunSummary(
                processed=1,
                completed=1,
                failed=0,
                callback_errors=0,
                persistence_errors=0,
                lifecycle_errors=0,
                notification_errors=0,
                retry_scheduled=0,
                terminal_failed=0,
                lease_lost=0,
                transition_unknown=0,
            )

        monkeypatch.setattr(main, "run_queue_loop", fake_run_queue_loop)

        main.main()

        assert loaded_paths == [tmp_path / "config.toml"]
        assert len(calls) == 1
        assert calls[0]["transaction_db_path"] == str(tmp_path / "rpacore.db")
        assert calls[0]["config"]["output_csv"] == str(
            tmp_path / "results" / "output.csv"
        )


def _adoption_config() -> dict[str, object]:
    return {
        "max_retries": 0,
        "log_level": "INFO",
        "transaction_db_path": "rpacore.db",
        "sample_data_dir": "sample_data",
        "results_dir": "results",
        "output_csv": "results/output.csv",
        "max_pages": 100,
        "queue": {"db_path": "queue.db", "lease_timeout": 30, "max_retries": 1},
    }


def test_validate_config_accepts_positive_queue_retry_and_rejects_lowercase_log_level():
    import main

    config = _adoption_config()
    main._validate_config(config)
    config["log_level"] = "info"

    with pytest.raises(SystemException, match="log_level"):
        main._validate_config(config)


@pytest.mark.parametrize(
    ("key", "value"),
    (("log_level", 0), ("queue", "queue.db")),
)
def test_validate_config_rejects_non_string_values_and_malformed_queue(key, value):
    import main

    config = _adoption_config()
    config[key] = value

    with pytest.raises(SystemException) as error:
        main._validate_config(config)
    assert key in str(error.value)


def test_validate_config_rejects_missing_dotted_queue_key():
    import main

    config = _adoption_config()
    queue = config["queue"]
    assert isinstance(queue, dict)
    del queue["db_path"]

    with pytest.raises(SystemException) as error:
        main._validate_config(config)
    assert "queue.db_path" in str(error.value)


@pytest.mark.parametrize(
    "key",
    ("transaction_db_path", "sample_data_dir", "results_dir", "output_csv", "queue.db_path"),
)
def test_load_example_config_rejects_paths_outside_project(tmp_path, monkeypatch, key):
    import main

    config = _adoption_config()
    if key == "queue.db_path":
        config["queue"]["db_path"] = "../outside/value"  # type: ignore[index]
    else:
        config[key] = "../outside/value"
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda _, *, require_file: config)

    with pytest.raises(SystemException, match="resolves outside root"):
        main._load_example_config()


def test_summary_values_projects_all_authoritative_delivery_counters():
    import main

    summary = QueueRunSummary(
        processed=1,
        completed=2,
        failed=3,
        callback_errors=4,
        persistence_errors=5,
        lifecycle_errors=6,
        notification_errors=7,
        retry_scheduled=8,
        terminal_failed=9,
        lease_lost=10,
        transition_unknown=11,
    )
    expected = {
        "processed": 1,
        "completed": 2,
        "failed": 3,
        "callback_errors": 4,
        "persistence_errors": 5,
        "lifecycle_errors": 6,
        "notification_errors": 7,
        "retry_scheduled": 8,
        "terminal_failed": 9,
        "lease_lost": 10,
        "transition_unknown": 11,
    }

    assert main._summary_values(summary) == expected
    assert {field.name for field in fields(QueueRunSummary)} == set(main._SUMMARY_FIELDS)
