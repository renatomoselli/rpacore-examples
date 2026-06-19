from __future__ import annotations

"""Integration tests for the full JSON Event Log Processor workflow."""

import json
import tempfile
from pathlib import Path

import main as app_main
from rpacore import Engine, ProcessContext, Status, Transaction, list_transactions, save_transaction
from skills.load_json_file import LoadJsonFile
from skills.validate_events import ValidateEvents
from skills.normalize_events import NormalizeEvents
from skills.write_output import WriteOutput
from skills.write_error_report import WriteErrorReport


class TestFullWorkflow:
    """Integration test for the full batch workflow."""

    def test_full_workflow_produces_correct_output(self):
        """Test the full pipeline: load, validate, normalize, write output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_dir = str(Path(tmpdir) / "inbox")
            results_dir = str(Path(tmpdir) / "results")
            db_path = str(Path(tmpdir) / "rpacore.db")

            Path(inbox_dir).mkdir()
            Path(results_dir).mkdir()

            # Create valid test events
            events = [
                {
                    "event_id": "evt-001",
                    "event_type": "info",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "source": "test-service",
                    "payload": {"message": "Hello"},
                },
                {
                    "event_id": "evt-002",
                    "event_type": "error",
                    "timestamp": "2024-01-01T01:00:00Z",
                    "source": "test-service",
                    "payload": {"error": "Something went wrong"},
                },
            ]
            (Path(inbox_dir) / "events_001.json").write_text(json.dumps(events), encoding="utf-8")

            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": db_path,
                "inbox_dir": inbox_dir,
                "results_dir": results_dir,
            }

            engine = Engine(max_retries=0)

            # Process the file
            shared_data = {
                "current_file": str(Path(inbox_dir) / "events_001.json"),
            }

            file_tx = Transaction(
                reference="json-file-events_001",
                state=shared_data,
                skills=[
                    LoadJsonFile(name="load_json_file", execution_order=1),
                    ValidateEvents(name="validate_events", execution_order=2),
                    NormalizeEvents(name="normalize_events", execution_order=3),
                    WriteOutput(name="write_output", execution_order=4),
                ],
            )
            engine.run(ProcessContext(transaction=file_tx, config=config))
            save_transaction(file_tx, db_path=db_path)

            assert file_tx.status == Status.SUCCESSFUL
            assert len(file_tx.state["normalized_events"]) == 2
            assert file_tx.state["normalized_events"][0]["severity"] == "INFO"
            assert file_tx.state["normalized_events"][1]["severity"] == "ERROR"

            # Verify output file
            output_file = Path(results_dir) / "events_001_cleaned.jsonl"
            assert output_file.exists()
            lines = output_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            record = json.loads(lines[0])
            assert record["event_id"] == "evt-001"
            assert record["version"] == "1.0"
            assert "processed_at" in record

    def test_main_continues_after_transaction_persistence_failure(self, tmp_path, monkeypatch):
        project_root = tmp_path / "project"
        inbox_dir = project_root / "inbox"
        results_dir = project_root / "results"
        inbox_dir.mkdir(parents=True)
        results_dir.mkdir()

        event = {
            "event_id": "evt-001",
            "event_type": "info",
            "timestamp": "2024-01-01T00:00:00Z",
            "source": "test-service",
            "payload": {},
        }
        (inbox_dir / "events_001.json").write_text(json.dumps([event]), encoding="utf-8")
        (inbox_dir / "events_002.json").write_text(json.dumps([event]), encoding="utf-8")

        config = {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": "rpacore.db",
            "inbox_dir": "inbox",
            "results_dir": "results",
        }
        original_save_transaction = app_main.save_transaction

        def flaky_save_transaction(tx, db_path):
            if tx.reference == "json-file-events_001":
                raise OSError("simulated persistence failure")
            return original_save_transaction(tx, db_path=db_path)

        monkeypatch.setattr(app_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(app_main, "load_config", lambda _: config)
        monkeypatch.setattr(app_main, "save_transaction", flaky_save_transaction)

        app_main.main()

        assert (results_dir / "events_001_cleaned.jsonl").exists()
        assert (results_dir / "events_002_cleaned.jsonl").exists()

        report = json.loads((results_dir / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 1
        assert report["successful"] == 1
        assert report["failed"] == 0
        assert report["persistence_error_count"] == 1
        assert report["persistence_errors"][0]["transaction_reference"] == "json-file-events_001"
        assert report["persistence_errors"][0]["status"] == "SUCCESSFUL"

        saved_txs = list_transactions(str(project_root / "rpacore.db"))
        assert any(tx.reference == "error-report" and tx.status == Status.SUCCESSFUL for tx in saved_txs)
        assert any(tx.reference == "json-file-events_002" and tx.status == Status.SUCCESSFUL for tx in saved_txs)

    def test_main_generates_empty_report_for_empty_inbox(self, tmp_path, monkeypatch):
        project_root = tmp_path / "project"
        (project_root / "inbox").mkdir(parents=True)
        (project_root / "results").mkdir()

        config = {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": "rpacore.db",
            "inbox_dir": "inbox",
            "results_dir": "results",
        }

        monkeypatch.setattr(app_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(app_main, "load_config", lambda _: config)

        app_main.main()

        report = json.loads((project_root / "results" / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["successful"] == 0
        assert report["failed"] == 0
        assert report["persistence_error_count"] == 0

        saved_txs = list_transactions(str(project_root / "rpacore.db"))
        assert any(tx.reference == "error-report" and tx.status == Status.SUCCESSFUL for tx in saved_txs)

    def test_main_refreshes_report_when_error_report_persistence_fails(self, tmp_path, monkeypatch):
        project_root = tmp_path / "project"
        (project_root / "inbox").mkdir(parents=True)
        (project_root / "results").mkdir()

        config = {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": "rpacore.db",
            "inbox_dir": "inbox",
            "results_dir": "results",
        }
        original_save_transaction = app_main.save_transaction

        def flaky_save_transaction(tx, db_path):
            if tx.reference == "error-report":
                raise OSError("simulated report persistence failure")
            return original_save_transaction(tx, db_path=db_path)

        monkeypatch.setattr(app_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(app_main, "load_config", lambda _: config)
        monkeypatch.setattr(app_main, "save_transaction", flaky_save_transaction)

        app_main.main()

        report = json.loads((project_root / "results" / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 0
        assert report["persistence_error_count"] == 1
        assert report["persistence_errors"][0]["transaction_reference"] == "error-report"

    def test_main_reports_all_files_failing_validation(self, tmp_path, monkeypatch):
        project_root = tmp_path / "project"
        inbox_dir = project_root / "inbox"
        results_dir = project_root / "results"
        inbox_dir.mkdir(parents=True)
        results_dir.mkdir()

        invalid_event = {
            "event_id": "evt-001",
            "timestamp": "2024-01-01T00:00:00Z",
            "source": "test-service",
        }
        (inbox_dir / "events_001.json").write_text(json.dumps([invalid_event]), encoding="utf-8")
        (inbox_dir / "events_002.json").write_text(json.dumps([invalid_event]), encoding="utf-8")

        config = {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": "rpacore.db",
            "inbox_dir": "inbox",
            "results_dir": "results",
        }

        monkeypatch.setattr(app_main, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(app_main, "load_config", lambda _: config)

        app_main.main()

        assert not (results_dir / "events_001_cleaned.jsonl").exists()
        assert not (results_dir / "events_002_cleaned.jsonl").exists()

        report = json.loads((results_dir / "error_report.json").read_text(encoding="utf-8"))
        assert report["total_transactions"] == 2
        assert report["successful"] == 0
        assert report["failed"] == 2
        assert sorted(failure["status"] for failure in report["failures"]) == ["FAILED", "FAILED"]
