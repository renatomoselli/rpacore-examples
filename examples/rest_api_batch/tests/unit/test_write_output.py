"""Unit tests for the WriteOutput skill."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpacore import SystemException
from skills.write_output import WriteOutput


class TestWriteOutput:
    """Test the WriteOutput skill."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_tx = Mock()
        self.mock_ctx = Mock()
        self.mock_ctx.data = {}
        self.mock_ctx.config = {}

    def test_writes_jsonl_record(self):
        """Test that WriteOutput appends a JSONL record to the output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "test_output.jsonl")
            self.mock_ctx.data = {
                "enriched_record": {
                    "postId": 1,
                    "title": "Test",
                    "body": "Test body",
                    "userId": 1,
                    "userName": "Test User",
                    "userEmail": "test@test.com",
                    "userCity": "Test City",
                }
            }
            self.mock_ctx.config = {"output_file": output_file}

            skill = WriteOutput("write_output", 4)
            skill.execute(self.mock_ctx)

            # Verify file was created and contains the record
            content = Path(output_file).read_text(encoding="utf-8")
            record = json.loads(content.strip())
            assert record["postId"] == 1
            assert record["userName"] == "Test User"

    def test_writes_multiple_records(self):
        """Test that WriteOutput can append multiple records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "test_output.jsonl")
            self.mock_ctx.config = {"output_file": output_file}

            # Write first record
            self.mock_ctx.data = {"enriched_record": {"postId": 1, "title": "First"}}
            skill = WriteOutput("write_output", 4)
            skill.execute(self.mock_ctx)

            # Write second record
            self.mock_ctx.data = {"enriched_record": {"postId": 2, "title": "Second"}}
            skill.execute(self.mock_ctx)

            # Verify both records exist
            content = Path(output_file).read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["postId"] == 1
            assert json.loads(lines[1])["postId"] == 2

    def test_raises_on_missing_record(self):
        """Test that WriteOutput raises when no enriched_record exists."""
        self.mock_ctx.data = {}

        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "No enriched_record" in str(exc_info.value)

    def test_raises_on_os_error(self):
        """Test that WriteOutput raises SystemException on OSError."""
        self.mock_ctx.data = {
            "enriched_record": {"postId": 1, "title": "Test"}
        }
        self.mock_ctx.config = {"output_file": "/nonexistent/dir/output.jsonl"}

        skill = WriteOutput("write_output", 4)

        with pytest.raises(SystemException) as exc_info:
            skill.execute(self.mock_ctx)

        assert "Failed to write" in str(exc_info.value)
