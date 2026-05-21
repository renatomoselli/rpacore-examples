"""Integration tests for partial failure scenarios."""

import json
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for importing skills
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from oref import Engine, ProcessContext, Status, Transaction, save_transaction
from skills.load_json_file import LoadJsonFile
from skills.validate_events import ValidateEvents
from skills.normalize_events import NormalizeEvents
from skills.write_output import WriteOutput
from skills.write_error_report import WriteErrorReport


class TestPartialFailure:
    """Test partial failure scenarios in the batch workflow."""

    def test_validation_failure_stops_execution(self):
        """Test that validation failure stops execution (unlike rest_api_batch pattern).

        This is a key behavioral difference from rest_api_batch:
        - rest_api_batch: BusinessException does NOT short-circuit (EnrichRecord still runs)
        - json_event_log_processor: validation failure DOES stop execution
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_dir = str(Path(tmpdir) / "inbox")
            results_dir = str(Path(tmpdir) / "results")
            db_path = str(Path(tmpdir) / "oref.db")

            Path(inbox_dir).mkdir()
            Path(results_dir).mkdir()

            # Create events with missing required field
            events = [
                {
                    "event_id": "evt-001",
                    "event_type": "info",  # valid
                    "timestamp": "2024-01-01T00:00:00Z",
                    "source": "test-service",
                },
                {
                    "event_id": "evt-002",
                    # Missing event_type — will cause validation failure
                    "timestamp": "2024-01-01T01:00:00Z",
                    "source": "test-service",
                },
            ]
            (Path(inbox_dir) / "events_001.json").write_text(json.dumps(events), encoding="utf-8")

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "inbox_dir": inbox_dir,
                "results_dir": results_dir,
            }

            engine = Engine(max_retries=0)

            shared_data["current_file"] = str(Path(inbox_dir) / "events_001.json")
            shared_data["results_dir"] = results_dir

            file_tx = Transaction(
                reference="json-file-events_001",
                skills=[
                    LoadJsonFile(name="load_json_file", execution_order=1),
                    ValidateEvents(name="validate_events", execution_order=2),
                    NormalizeEvents(name="normalize_events", execution_order=3),
                    WriteOutput(name="write_output", execution_order=4),
                ],
            )
            engine.run(ProcessContext(transaction=file_tx, config=config, data=shared_data))
            save_transaction(file_tx, db_path=db_path)

            # Transaction should fail
            assert file_tx.status == Status.FAILED

            # No output file should be created
            output_file = Path(results_dir) / "events_001_cleaned.jsonl"
            assert not output_file.exists()

            # NormalizeEvents should NOT have run (no normalized_events)
            assert "normalized_events" not in shared_data

    def test_successful_file_produces_output(self):
        """Test that a valid file produces output even when another file fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_dir = str(Path(tmpdir) / "inbox")
            results_dir = str(Path(tmpdir) / "results")
            db_path = str(Path(tmpdir) / "oref.db")

            Path(inbox_dir).mkdir()
            Path(results_dir).mkdir()

            # Valid events
            valid_events = [
                {
                    "event_id": "evt-001",
                    "event_type": "info",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "source": "test-service",
                },
            ]
            (Path(inbox_dir) / "events_001.json").write_text(json.dumps(valid_events), encoding="utf-8")

            # Invalid events (missing required field)
            invalid_events = [
                {
                    "event_id": "evt-002",
                    # Missing event_type
                    "timestamp": "2024-01-01T01:00:00Z",
                    "source": "test-service",
                },
            ]
            (Path(inbox_dir) / "events_002.json").write_text(json.dumps(invalid_events), encoding="utf-8")

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "inbox_dir": inbox_dir,
                "results_dir": results_dir,
            }

            engine = Engine(max_retries=0)
            successful = 0
            failed = 0

            for json_file in sorted(Path(inbox_dir).glob("*.json")):
                shared_data["current_file"] = str(json_file)
                shared_data["results_dir"] = results_dir
                shared_data.pop("events", None)
                shared_data.pop("normalized_events", None)
                shared_data.pop("validation_failed", None)

                file_tx = Transaction(
                    reference=f"json-file-{json_file.stem}",
                    skills=[
                        LoadJsonFile(name="load_json_file", execution_order=1),
                        ValidateEvents(name="validate_events", execution_order=2),
                        NormalizeEvents(name="normalize_events", execution_order=3),
                        WriteOutput(name="write_output", execution_order=4),
                    ],
                )
                engine.run(ProcessContext(transaction=file_tx, config=config, data=shared_data))
                save_transaction(file_tx, db_path=db_path)

                if file_tx.status == Status.SUCCESSFUL:
                    successful += 1
                else:
                    failed += 1

            assert successful == 1
            assert failed == 1

            # Only valid file should have output
            assert (Path(results_dir) / "events_001_cleaned.jsonl").exists()
            assert not (Path(results_dir) / "events_002_cleaned.jsonl").exists()
