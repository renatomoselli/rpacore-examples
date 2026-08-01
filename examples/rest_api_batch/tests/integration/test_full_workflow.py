from __future__ import annotations

"""
Integration test for the full REST API Batch Processor workflow.

This test mocks all requests.get calls to avoid hitting the real API,
then runs the full transaction pipeline and verifies the output.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path for importing skills
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import POST_DEFINITION_IDENTITY
from skills.fetch_posts import FetchPosts
from skills.fetch_user import FetchUser
from skills.validate_post import ValidatePost
from skills.enrich_record import EnrichRecord
from skills.write_output import WriteOutput


# Sample data matching JSONPlaceholder structure
SAMPLE_POSTS = [
    {
        "id": 1,
        "title": "sunt aut facere repellat provident occaecati excepturi optio reprehenderit",
        "body": "quia et suscipit\nsuscipit recusandae consequuntur expedita et cum",
        "userId": 1,
    },
    {
        "id": 2,
        "title": "qui est esse",
        "body": "est rerum tempore vitae\nsequi sint nihil reprehenderit dolor beatae ea dolores neque",
        "userId": 2,
    },
    {
        "id": 3,
        "title": "fugiat veniam minus",
        "body": "et porro tempora",
        "userId": 1,
    },
]

SAMPLE_USERS = {
    1: {
        "id": 1,
        "name": "Leanne Graham",
        "email": "Sincere@april.biz",
        "address": {"city": "Gwenborough"},
    },
    2: {
        "id": 2,
        "name": "Clementine Bauch",
        "email": "Nathan@yesenia.net",
        "address": {"city": "South Elvis"},
    },
}


def _make_mock_response(data):
    """Create a mock requests.Response object."""
    from unittest.mock import Mock
    mock_response = Mock()
    mock_response.json.return_value = data
    mock_response.raise_for_status.return_value = None
    return mock_response


def _mock_get(url, **kwargs):
    """Single mock for requests.get that dispatches based on URL.

    Both fetch_posts and fetch_user share the same requests module,
    so we need one mock that handles both /posts and /users endpoints.
    """
    if "/posts" in url:
        return _make_mock_response(SAMPLE_POSTS)
    user_id = int(url.rstrip("/").split("/")[-1])
    return _make_mock_response(SAMPLE_USERS[user_id])


class TestFullWorkflow:
    """Integration test for the full batch workflow."""

    def test_fixture_mode_full_workflow_without_http(self, tmp_path):
        """Test default fixture flow: invalid post is skipped and artifacts are attached."""
        from rpacore import Engine, ProcessContext, Status, Transaction

        config = {
            "max_retries": 0,
            "log_level": "WARNING",
            "transaction_db_path": str(tmp_path / "rpacore.db"),
            "output_file": str(tmp_path / "output.jsonl"),
            "api_mode": "fixture",
        }

        engine = Engine(max_retries=0)
        setup_tx = Transaction(
            reference="fetch-posts",
            state={},
            skills=[FetchPosts(name="fetch_posts", execution_order=1)],
        )
        with patch("requests.get") as mock_get:
            engine.run(ProcessContext(transaction=setup_tx, config=config))
        mock_get.assert_not_called()
        assert setup_tx.status == Status.SUCCESSFUL

        post_statuses = {}
        artifact_count = 0
        for post in setup_tx.state["posts"]:
            post_tx = Transaction(
                reference=f"post-{post['id']}",
                state={"current_post": post},
                skills=[
                    ValidatePost(name="validate_post", execution_order=1),
                    FetchUser(name="fetch_user", execution_order=2),
                    EnrichRecord(name="enrich_record", execution_order=3),
                    WriteOutput(name="write_output", execution_order=4),
                ],
            )
            with patch("requests.get") as mock_get:
                engine.run(ProcessContext(transaction=post_tx, config=config))
            mock_get.assert_not_called()
            post_statuses[post["id"]] = post_tx.status
            artifact_count += len(post_tx.artifacts)

        output_lines = Path(config["output_file"]).read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["postId"] for line in output_lines] == [1, 3]
        assert post_statuses[2] == Status.FAILED
        assert artifact_count == 2

    @patch("requests.get", side_effect=_mock_get)
    def test_live_mode_full_workflow_with_mocked_http(self, mock_get):
        """Test the live-mode pipeline while replacing external HTTP responses."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "output.jsonl")
            db_path = str(Path(tmpdir) / "rpacore.db")

            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": db_path,
                "output_file": output_file,
                "api_mode": "live",
            }

            # --- Setup transaction: fetch posts ---
            from rpacore import Engine, ProcessContext, Status, Transaction, save_transaction

            setup_tx = Transaction(
                reference="fetch-posts",
                state={},
                skills=[FetchPosts(name="fetch_posts", execution_order=1)],
            )
            engine = Engine(max_retries=0)
            engine.run(ProcessContext(transaction=setup_tx, config=config))
            assert setup_tx.status == Status.SUCCESSFUL
            posts = setup_tx.state.get("posts", [])
            assert len(posts) == 3

            # --- Per-post transactions ---
            results = []
            for post in posts:
                post_tx = Transaction(
                    reference=f"post-{post['id']}",
                    definition_identity=POST_DEFINITION_IDENTITY,
                    state={"current_post": post},
                    skills=[
                        ValidatePost(name="validate_post", execution_order=1),
                        FetchUser(name="fetch_user", execution_order=2),
                        EnrichRecord(name="enrich_record", execution_order=3),
                        WriteOutput(name="write_output", execution_order=4),
                    ],
                )
                engine.run(ProcessContext(transaction=post_tx, config=config))
                save_transaction(post_tx, db_path=db_path)

                assert post_tx.status == Status.SUCCESSFUL
                results.append(post_tx.state["enriched_record"])

            # --- Verify output ---
            assert len(results) == 3
            assert results[0]["postId"] == 1
            assert results[0]["userName"] == "Leanne Graham"
            assert results[0]["userCity"] == "Gwenborough"
            assert results[1]["postId"] == 2
            assert results[1]["userName"] == "Clementine Bauch"
            assert results[1]["userCity"] == "South Elvis"
            assert results[2]["postId"] == 3
            assert results[2]["userName"] == "Leanne Graham"  # userId=1

            # Verify JSONL file
            content = Path(output_file).read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 3
            for i, line in enumerate(lines):
                record = json.loads(line)
                assert record["postId"] == SAMPLE_POSTS[i]["id"]
                assert "userName" in record
                assert "userEmail" in record
                assert "userCity" in record
            assert mock_get.call_count == 4

    @patch("requests.get")
    def test_partial_batch_failure_with_empty_title(self, mock_get):
        """Test that a post with empty title fails and is NOT in output (stop=True).

        With stop=True, BusinessException short-circuit prevents EnrichRecord
        and WriteOutput from running, so the failed post is excluded from output.
        """
        partial_posts = [
            {
                "id": 1,
                "title": "Valid Post",
                "body": "Body 1",
                "userId": 1,
            },
            {
                "id": 2,
                "title": "",
                "body": "Body 2",
                "userId": 2,
            },  # Empty title → fails
            {
                "id": 3,
                "title": "Also Valid",
                "body": "Body 3",
                "userId": 1,
            },
        ]

        def _partial_mock_get(url, **kwargs):
            if "/posts" in url:
                return _make_mock_response(partial_posts)
            user_id = int(url.rstrip("/").split("/")[-1])
            return _make_mock_response(SAMPLE_USERS[user_id])

        mock_get.side_effect = _partial_mock_get

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "output.jsonl")
            db_path = str(Path(tmpdir) / "rpacore.db")

            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "transaction_db_path": db_path,
                "output_file": output_file,
                "api_mode": "live",
            }

            from rpacore import (
                Engine,
                ProcessContext,
                Status,
                Transaction,
                save_transaction,
            )

            # Setup
            setup_tx = Transaction(
                reference="fetch-posts",
                state={},
                skills=[FetchPosts(name="fetch_posts", execution_order=1)],
            )
            engine = Engine(max_retries=0)
            engine.run(ProcessContext(transaction=setup_tx, config=config))
            assert setup_tx.status == Status.SUCCESSFUL

            # Process posts — post 2 fails (BusinessException with stop=True),
            # 1 and 3 succeed
            failed_ids = []
            post_statuses = {}  # post_id → transaction status
            for post in setup_tx.state["posts"]:
                post_tx = Transaction(
                    reference=f"post-{post['id']}",
                    definition_identity=POST_DEFINITION_IDENTITY,
                    state={"current_post": post},
                    skills=[
                        ValidatePost(name="validate_post", execution_order=1),
                        FetchUser(name="fetch_user", execution_order=2),
                        EnrichRecord(name="enrich_record", execution_order=3),
                        WriteOutput(name="write_output", execution_order=4),
                    ],
                )
                engine.run(ProcessContext(transaction=post_tx, config=config))
                save_transaction(post_tx, db_path=db_path)

                post_statuses[post["id"]] = post_tx.status
                if post_tx.status != Status.SUCCESSFUL:
                    failed_ids.append(post["id"])

            # Verify: posts 1 and 3 succeed, post 2 fails
            assert 2 in failed_ids
            assert post_statuses[2] == Status.FAILED
            assert post_statuses[1] == Status.SUCCESSFUL
            assert post_statuses[3] == Status.SUCCESSFUL

            # Verify JSONL file — post 2 is NOT in output due to stop=True short-circuit
            content = Path(output_file).read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 2
            post_ids_in_output = [json.loads(line)["postId"] for line in lines]
            assert 1 in post_ids_in_output
            assert 3 in post_ids_in_output
            assert 2 not in post_ids_in_output
