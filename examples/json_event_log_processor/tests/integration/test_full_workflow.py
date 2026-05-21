"""Integration tests for the full JSON Event Log Processor workflow."""

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


class TestFullWorkflow:
    """Integration test for the full batch workflow."""

    def test_full_workflow_produces_correct_output(self):
        """Test the full pipeline: load, validate, normalize, write output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inbox_dir = str(Path(tmpdir) / "inbox")
            results_dir = str(Path(tmpdir) / "results")
            db_path = str(Path(tmpdir) / "oref.db")

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

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "inbox_dir": inbox_dir,
                "results_dir": results_dir,
            }

            engine = Engine(max_retries=0)

            # Process the file
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

            assert file_tx.status == Status.SUCCESSFUL
            assert len(shared_data["normalized_events"]) == 2
            assert shared_data["normalized_events"][0]["severity"] == "INFO"
            assert shared_data["normalized_events"][1]["severity"] == "ERROR"

            # Verify output file
            output_file = Path(results_dir) / "events_001_cleaned.jsonl"
            assert output_file.exists()
            lines = output_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            record = json.loads(lines[0])
            assert record["event_id"] == "evt-001"
            assert record["version"] == "1.0"
            assert "processed_at" in record
