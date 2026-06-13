"""Unit tests for the WriteOutput skill."""

import json
import tempfile
from pathlib import Path

import pytest

from rpacore import ProcessContext, SystemException, Transaction
from skills.write_output import WriteOutput


class TestWriteOutput:
    """Test the WriteOutput skill."""

    def test_writes_jsonl_record(self):
        """Test that WriteOutput appends a JSONL record to the output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "test_output.jsonl")
            record = {
                "postId": 1,
                "title": "Test",
                "body": "Test body",
                "userId": 1,
                "userName": "Test User",
                "userEmail": "test@test.com",
                "userCity": "Test City",
            }
            transaction = Transaction(
                reference="test",
                state={"enriched_record": record},
            )
            ctx = ProcessContext(transaction=transaction, config={"output_file": output_file})

            skill = WriteOutput("write_output", 4)
            skill.execute(ctx)

            # Verify file was created and contains the record
            content = Path(output_file).read_text(encoding="utf-8")
            parsed = json.loads(content.strip())
            assert parsed["postId"] == 1
            assert parsed["userName"] == "Test User"
            assert len(ctx.transaction.artifacts) == 1
            artifact = ctx.transaction.artifacts[0]
            assert artifact.name == "output-jsonl"
            assert artifact.metadata["post_id"] == 1

    def test_writes_multiple_records(self):
        """Test that WriteOutput can append multiple records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "test_output.jsonl")

            # Write first record
            transaction = Transaction(
                reference="test",
                state={"enriched_record": {"postId": 1, "title": "First"}},
            )
            ctx = ProcessContext(transaction=transaction, config={"output_file": output_file})

            skill = WriteOutput("write_output", 4)
            skill.execute(ctx)

            # Write second record
            transaction.state["enriched_record"] = {"postId": 2, "title": "Second"}
            skill.execute(ctx)

            # Verify both records exist
            content = Path(output_file).read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["postId"] == 1
            assert json.loads(lines[1])["postId"] == 2

    def test_skips_duplicate_post_id(self):
        """Test retry-safe duplicate suppression by postId."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "test_output.jsonl"
            output_file.write_text(json.dumps({"postId": 1, "title": "First"}) + "\n", encoding="utf-8")

            transaction = Transaction(
                reference="test",
                state={"enriched_record": {"postId": 1, "title": "First retry"}},
            )
            ctx = ProcessContext(transaction=transaction, config={"output_file": str(output_file)})

            skill = WriteOutput("write_output", 4)
            skill.execute(ctx)

            lines = output_file.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            assert ctx.transaction.artifacts[0].metadata["deduplicated"] is True

    def test_raises_on_missing_record(self):
        """Test that WriteOutput raises when no enriched_record exists."""
        transaction = Transaction(reference="test", state={})
        ctx = ProcessContext(transaction=transaction, config={"output_file": "output.jsonl"})

        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)

        assert "Missing required state" in str(exc_info.value)

    def test_raises_on_os_error(self):
        """Test that WriteOutput raises SystemException on OSError."""
        transaction = Transaction(
            reference="test",
            state={"enriched_record": {"postId": 1, "title": "Test"}},
        )
        ctx = ProcessContext(
            transaction=transaction,
            config={"output_file": "/nonexistent/dir/output.jsonl"},
        )

        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(ctx)

        assert "Failed to write" in str(exc_info.value)
