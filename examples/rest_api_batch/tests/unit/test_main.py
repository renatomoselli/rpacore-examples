from __future__ import annotations

"""Unit tests for main.py config validation."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpacore import (
    BusinessException,
    Engine,
    OutcomeCategory,
    ProcessContext,
    RetryDisposition,
    Step,
    SystemException,
    Transaction,
)


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

        assert "expected int" in str(exc_info.value)

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

        assert "expected int" in str(exc_info.value)

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

        assert "expected int >= 0" in str(exc_info.value)

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

    @pytest.mark.parametrize(
        "key",
        ["log_level", "transaction_db_path", "output_file", "api_mode"],
    )
    def test_rejects_blank_string_config(self, key):
        """Test that string configuration values cannot be empty or whitespace."""
        from main import _validate_config

        config = {
            "max_retries": 0,
            "log_level": "INFO",
            "transaction_db_path": "rpacore.db",
            "output_file": "output.jsonl",
            "api_mode": "fixture",
        }
        config[key] = "   "

        with pytest.raises(SystemException, match="must be a non-empty string"):
            _validate_config(config)


class TestMainRuntime:
    def test_main_preserves_existing_output_when_setup_fails(self, tmp_path, monkeypatch):
        """Test that failed setup does not erase the previous successful output."""
        import main

        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

        class FailingFetchPosts(Step):
            def execute(self, ctx):
                raise SystemException("setup failed", action=self.name)

        existing = json.dumps({"postId": 999}) + "\n"
        output_file = tmp_path / "output.jsonl"
        output_file.write_text(existing, encoding="utf-8")

        monkeypatch.setattr(main, "FetchPosts", FailingFetchPosts)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
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

        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)

        output_file = tmp_path / "output.jsonl"
        output_file.write_text(json.dumps({"postId": 999}) + "\n", encoding="utf-8")

        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
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
        assert list(tmp_path.glob("*.backup")) == []

    @pytest.mark.parametrize(
        "output_value",
        ["../outside.jsonl", str(Path("..") / "outside.jsonl")],
    )
    def test_main_rejects_output_outside_project_root(
        self, tmp_path, monkeypatch, output_value
    ):
        """Test that a traversing output path cannot delete an external file."""
        import main

        project_root = tmp_path / "project"
        project_root.mkdir()
        outside_file = tmp_path / "outside.jsonl"
        outside_file.write_text("keep me\n", encoding="utf-8")

        monkeypatch.setattr(main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": output_value,
                "api_mode": "fixture",
            },
        )

        with pytest.raises(SystemException, match="resolves outside root"):
            main.main()

        assert outside_file.read_text(encoding="utf-8") == "keep me\n"

    def test_main_empty_posts_replaces_prior_output_with_no_output(
        self, tmp_path, monkeypatch
    ):
        """Test that a successful empty batch publishes an empty result set."""
        import main

        class EmptyFetchPosts(Step):
            def execute(self, ctx):
                ctx.state["posts"] = []

        output_file = tmp_path / "output.jsonl"
        output_file.write_text(json.dumps({"postId": 999}) + "\n", encoding="utf-8")
        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(main, "FetchPosts", EmptyFetchPosts)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": "output.jsonl",
                "api_mode": "fixture",
            },
        )

        main.main()

        assert not output_file.exists()
        assert list(tmp_path.glob("*.backup")) == []

    def test_main_all_business_failures_publish_no_output(
        self, tmp_path, monkeypatch
    ):
        """Test that an all-rejected batch completes without publishing JSONL."""
        import main

        class InvalidFetchPosts(Step):
            def execute(self, ctx):
                ctx.state["posts"] = [
                    {"id": 1, "title": "", "body": "Body", "userId": 1},
                    {"id": 2, "title": "   ", "body": "Body", "userId": 2},
                ]

        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(main, "FetchPosts", InvalidFetchPosts)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": "output.jsonl",
                "api_mode": "fixture",
            },
        )

        main.main()

        assert not (tmp_path / "output.jsonl").exists()

    def test_main_reports_output_preservation_failure(self, tmp_path, monkeypatch):
        """Test that failure to preserve prior output aborts before processing."""
        import main

        output_file = tmp_path / "output.jsonl"
        output_file.write_text("keep me\n", encoding="utf-8")
        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(main, "save_transaction", Mock())
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": "output.jsonl",
                "api_mode": "fixture",
            },
        )
        monkeypatch.setattr(
            main.os,
            "replace",
            Mock(side_effect=OSError("permission denied")),
        )

        with pytest.raises(SystemException, match="Could not preserve existing output"):
            main.main()

        assert output_file.read_text(encoding="utf-8") == "keep me\n"

    def test_main_restores_previous_output_when_post_persistence_fails(
        self, tmp_path, monkeypatch
    ):
        """Test that JSONL and SQLite cannot diverge after an audit failure."""
        import main

        existing = json.dumps({"postId": 999}) + "\n"
        output_file = tmp_path / "output.jsonl"
        output_file.write_text(existing, encoding="utf-8")
        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": "output.jsonl",
                "api_mode": "fixture",
            },
        )
        monkeypatch.setattr(
            main,
            "save_transaction",
            Mock(
                side_effect=[
                    None,
                    sqlite3.OperationalError("database is locked"),
                ]
            ),
        )

        with pytest.raises(SystemException, match="Could not persist transaction"):
            main.main()

        assert output_file.read_text(encoding="utf-8") == existing
        assert list(tmp_path.glob("*.backup")) == []

    def test_main_restores_previous_output_after_exhausted_step_retries(
        self, tmp_path, monkeypatch
    ):
        """Test that a technical post failure aborts without publishing partial output."""
        import main

        class FailingWriteOutput(Step):
            def execute(self, ctx):
                raise SystemException("disk full", action=self.name)

        existing = json.dumps({"postId": 999}) + "\n"
        output_file = tmp_path / "output.jsonl"
        output_file.write_text(existing, encoding="utf-8")
        monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(main, "WriteOutput", FailingWriteOutput)
        monkeypatch.setattr(main, "save_transaction", Mock())
        monkeypatch.setattr(
            main,
            "load_config",
            lambda _, *, require_file: {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": "rpacore.db",
                "output_file": "output.jsonl",
                "api_mode": "fixture",
            },
        )

        with pytest.raises(SystemException, match="exhausted retries"):
            main.main()

        assert output_file.read_text(encoding="utf-8") == existing
        assert list(tmp_path.glob("*.backup")) == []

    def test_persist_transaction_raises_when_audit_save_fails(
        self, tmp_path, monkeypatch
    ):
        """Test that persistence failure is not reported as batch success."""
        import main

        transaction = Transaction(reference="test", state={})
        monkeypatch.setattr(
            main,
            "save_transaction",
            Mock(side_effect=sqlite3.OperationalError("database is locked")),
        )

        with pytest.raises(SystemException, match="Could not persist test transaction"):
            main._persist_transaction(
                transaction,
                db_path=str(tmp_path / "rpacore.db"),
                description="test transaction",
            )


def test_load_example_config_is_rooted_and_does_not_mutate_source(tmp_path, monkeypatch) -> None:
    import main

    config = {
        "max_retries": 2,
        "log_level": "INFO",
        "transaction_db_path": "state/rpacore.db",
        "output_file": "output/output.jsonl",
        "api_mode": "fixture",
    }
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda path, *, require_file: dict(config))

    loaded = main._load_example_config()

    assert config["transaction_db_path"] == "state/rpacore.db"
    assert config["output_file"] == "output/output.jsonl"
    assert loaded["transaction_db_path"] == str(tmp_path / "state" / "rpacore.db")
    assert loaded["output_file"] == str(tmp_path / "output" / "output.jsonl")


def test_load_example_config_rejects_database_path_outside_project(tmp_path, monkeypatch) -> None:
    import main

    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        main,
        "load_config",
        lambda path, *, require_file: {
            "max_retries": 2,
            "log_level": "INFO",
            "transaction_db_path": "../outside/rpacore.db",
            "output_file": "output/output.jsonl",
            "api_mode": "fixture",
        },
    )

    with pytest.raises(SystemException, match="resolves outside root"):
        main._load_example_config()


def test_post_rollback_uses_canonical_business_outcome() -> None:
    from main import _post_requires_batch_rollback
    from steps.validate_post import ValidatePost

    transaction = Transaction(
        reference="post-invalid",
        state={"current_post": {"id": 1, "title": "", "body": "body", "userId": 1}},
        steps=[ValidatePost(name="validate_post", execution_order=1)],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=transaction, config={}))

    assert transaction.outcome_category is OutcomeCategory.BUSINESS_FAILED
    assert transaction.retry_disposition is RetryDisposition.NOT_REQUESTED
    assert transaction.failure_code == "rest_api_batch.post.invalid"
    assert transaction.retry_count == 0
    assert _post_requires_batch_rollback(transaction) is False


def test_post_rollback_uses_final_canonical_outcome_after_retry() -> None:
    from main import _post_requires_batch_rollback

    class ChangesFailureKind(Step):
        def execute(self, ctx) -> None:
            if ctx.transaction.retry_count == 0:
                raise SystemException("transient", action=self.name, code="rest_api_batch.http.request_failed")
            raise BusinessException("rejected", action=self.name, halts_remaining_steps=True, code="rest_api_batch.post.invalid")

    transaction = Transaction(reference="post-retried", steps=[ChangesFailureKind("post", 1)])
    Engine(max_retries=2).run(ProcessContext(transaction=transaction, config={}))

    assert transaction.outcome_category is OutcomeCategory.BUSINESS_FAILED
    assert transaction.retry_disposition is RetryDisposition.NOT_REQUESTED
    assert transaction.failure_code == "rest_api_batch.post.invalid"
    assert transaction.retry_count == 1
    assert _post_requires_batch_rollback(transaction) is False


def test_post_rollback_requires_zero_retry_system_failure() -> None:
    from main import _post_requires_batch_rollback

    class AlwaysFails(Step):
        def execute(self, ctx) -> None:
            raise SystemException(
                "request failed",
                action=self.name,
                code="rest_api_batch.http.request_failed",
            )

    transaction = Transaction(reference="post-zero-retry", steps=[AlwaysFails("post", 1)])
    Engine(max_retries=0).run(ProcessContext(transaction=transaction, config={}))

    assert transaction.outcome_category is OutcomeCategory.SYSTEM_FAILED
    assert transaction.retry_disposition is RetryDisposition.RETRY_EXHAUSTED
    assert transaction.failure_code == "rest_api_batch.http.request_failed"
    assert transaction.retry_count == 0
    assert _post_requires_batch_rollback(transaction) is True


def test_post_rollback_requires_exhausted_fetch_failure_and_preserves_output(
    tmp_path, monkeypatch
) -> None:
    from main import _post_requires_batch_rollback
    from steps.enrich_record import EnrichRecord
    from steps.fetch_user import FetchUser
    from steps.validate_post import ValidatePost
    from steps.write_output import WriteOutput

    calls = 0

    def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise SystemException(
            "request timed out",
            action="fetch_user",
            code="rest_api_batch.http.request_failed",
        )

    monkeypatch.setattr("steps.fetch_user.fetch_json", timeout)
    output_file = tmp_path / "output.jsonl"
    transaction = Transaction(
        reference="post-timeout",
        state={
            "current_post": {
                "id": 1,
                "title": "Valid title",
                "body": "Valid body",
                "userId": 1,
            }
        },
        steps=[
            ValidatePost(name="validate_post", execution_order=1),
            FetchUser(name="fetch_user", execution_order=2),
            EnrichRecord(name="enrich_record", execution_order=3),
            WriteOutput(name="write_output", execution_order=4),
        ],
    )

    Engine(max_retries=2).run(
        ProcessContext(
            transaction=transaction,
            config={"api_mode": "live", "output_file": str(output_file)},
        )
    )

    assert calls == 3
    assert transaction.outcome_category is OutcomeCategory.SYSTEM_FAILED
    assert transaction.retry_disposition is RetryDisposition.RETRY_EXHAUSTED
    assert transaction.failure_code == "rest_api_batch.http.request_failed"
    assert transaction.retry_count == 2
    assert _post_requires_batch_rollback(transaction) is True
    assert not output_file.exists()
