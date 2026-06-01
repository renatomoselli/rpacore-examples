"""
Integration test for the full REST API Batch Processor workflow.

This test mocks all requests.get calls to avoid hitting the real API,
then runs the full transaction pipeline and verifies the output.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add parent directory to path for importing skills
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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

    @patch("requests.get", side_effect=_mock_get)
    def test_full_workflow_produces_correct_output(self, mock_get):
        """Test the full pipeline: fetch posts, fetch users, validate, enrich, write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "output.jsonl")
            db_path = str(Path(tmpdir) / "rpacore.db")

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "output_file": output_file,
            }

            # --- Setup transaction: fetch posts ---
            from rpacore import Engine, ProcessContext, Status, Transaction, save_transaction

            setup_tx = Transaction(
                reference="fetch-posts",
                skills=[FetchPosts(name="fetch_posts", execution_order=1)],
            )
            engine = Engine(max_retries=0)
            engine.run(ProcessContext(transaction=setup_tx, config=config, data=shared_data))
            assert setup_tx.status == Status.SUCCESSFUL
            assert len(shared_data["posts"]) == 3

            # --- Per-post transactions ---
            results = []
            for post in shared_data["posts"]:
                shared_data["current_post"] = post

                # Clear stale shared state from previous transaction
                shared_data.pop("current_user", None)
                shared_data.pop("enriched_record", None)

                post_tx = Transaction(
                    reference=f"post-{post['id']}",
                    skills=[
                        FetchUser(name="fetch_user", execution_order=1),
                        ValidatePost(name="validate_post", execution_order=2),
                        EnrichRecord(name="enrich_record", execution_order=3),
                        WriteOutput(name="write_output", execution_order=4),
                    ],
                )
                engine.run(ProcessContext(transaction=post_tx, config=config, data=shared_data))
                save_transaction(post_tx, db_path=db_path)

                assert post_tx.status == Status.SUCCESSFUL
                results.append(shared_data["enriched_record"])

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

    @patch("requests.get")
    def test_partial_batch_failure_with_empty_title(self, mock_get):
        """Test that a post with empty title fails but other posts succeed.

        Note: BusinessException does not short-circuit skill execution.
        EnrichRecord and WriteOutput still run for the failed post,
        so the output file contains ALL records including the failed one.
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

            shared_data = {}
            config = {
                "max_retries": 0,
                "log_level": "WARNING",
                "db_path": db_path,
                "output_file": output_file,
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
                skills=[FetchPosts(name="fetch_posts", execution_order=1)],
            )
            engine = Engine(max_retries=0)
            engine.run(
                ProcessContext(transaction=setup_tx, config=config, data=shared_data)
            )
            assert setup_tx.status == Status.SUCCESSFUL

            # Process posts — post 2 fails (BusinessException), 1 and 3 succeed
            results = []
            failed_ids = []
            post_statuses = {}  # post_id → transaction status
            for post in shared_data["posts"]:
                shared_data["current_post"] = post
                shared_data.pop("current_user", None)
                shared_data.pop("enriched_record", None)

                post_tx = Transaction(
                    reference=f"post-{post['id']}",
                    skills=[
                        FetchUser(name="fetch_user", execution_order=1),
                        ValidatePost(name="validate_post", execution_order=2),
                        EnrichRecord(
                            name="enrich_record", execution_order=3
                        ),
                        WriteOutput(name="write_output", execution_order=4),
                    ],
                )
                engine.run(
                    ProcessContext(transaction=post_tx, config=config, data=shared_data)
                )
                save_transaction(post_tx, db_path=db_path)

                post_statuses[post["id"]] = post_tx.status
                if post_tx.status == Status.SUCCESSFUL:
                    results.append(shared_data["enriched_record"])
                else:
                    failed_ids.append(post["id"])

            # Verify: posts 1 and 3 succeed, post 2 fails (BusinessException)
            # Note: BusinessException does NOT short-circuit skill execution —
            # EnrichRecord and WriteOutput still run for the failed post,
            # so the output file will contain ALL 3 records.
            assert len(results) == 2
            assert 1 in [r["postId"] for r in results]
            assert 3 in [r["postId"] for r in results]
            assert 2 in failed_ids

            # Verify post 2's transaction status is FAILED (not retried)
            assert post_statuses[2] == Status.FAILED
            assert post_statuses[1] == Status.SUCCESSFUL
            assert post_statuses[3] == Status.SUCCESSFUL

            # Verify JSONL file contains ALL 3 records including the failed post
            # (BusinessException does not short-circuit; EnrichRecord + WriteOutput still run)
            content = Path(output_file).read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 3
            post_ids_in_output = [json.loads(line)["postId"] for line in lines]
            assert 1 in post_ids_in_output
            assert 2 in post_ids_in_output
            assert 3 in post_ids_in_output
