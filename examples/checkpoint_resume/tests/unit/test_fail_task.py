from __future__ import annotations

import pytest

from rpacore import Status, SystemException

from skills.fail_task import FailTask


class TestFailTask:
    """Tests for the FailTask skill."""

    def test_execute_raises_when_fail_on_first_run_true(self, run_skill) -> None:
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            config={"fail_on_first_run": True},
        )
        assert tx.status == Status.FAILED
        assert len(tx.failed_skills()) == 1
        assert isinstance(tx.failed_skills()[0].exceptions[-1], SystemException)
        assert "Simulated failure on first run" in str(
            tx.failed_skills()[0].exceptions[-1]
        )

    def test_execute_succeeds_when_fail_on_first_run_false(self, run_skill) -> None:
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state={"counter": {"value": 1, "timestamp": "2024-01-01T00:00:00+00:00"}},
            config={"fail_on_first_run": False},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["counter"]["value"] == 2
        assert tx.state["resume_complete"] is True

    def test_execute_sets_resume_complete(self, run_skill) -> None:
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state={"counter": {"value": 0}},
            config={"fail_on_first_run": False},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["resume_complete"] is True

    def test_execute_does_not_modify_state_on_failure(self, run_skill) -> None:
        initial_state = {"counter": {"value": 1}}
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state=initial_state,
            config={"fail_on_first_run": True},
        )
        # State should be unchanged after the exception
        assert tx.state == initial_state

    def test_execute_requires_counter_state(self, run_skill) -> None:
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state={},  # No counter key
            config={"fail_on_first_run": False},
        )
        assert tx.status == Status.FAILED
        assert "counter" in str(tx.failed_skills()[0].exceptions[-1]).lower()

    def test_execute_with_missing_value_key(self, run_skill) -> None:
        """Counter dict exists but has no 'value' key — should default to 0."""
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state={"counter": {"timestamp": "2024-01-01T00:00:00+00:00"}},
            config={"fail_on_first_run": False},
        )
        assert tx.status == Status.SUCCESSFUL
        assert tx.state["counter"]["value"] == 1
        assert tx.state["resume_complete"] is True

    def test_execute_rejects_non_dict_counter(self, run_skill) -> None:
        tx = run_skill(
            FailTask(name="fail_task", execution_order=2),
            state={"counter": "bad_type"},
            config={"fail_on_first_run": False},
        )

        assert tx.status == Status.FAILED
        assert isinstance(tx.failed_skills()[0].exceptions[-1], SystemException)
