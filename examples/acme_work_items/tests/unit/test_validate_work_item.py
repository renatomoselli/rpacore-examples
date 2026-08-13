from __future__ import annotations

import pytest
from rpacore import BusinessException, Status

from steps.validate_work_item import ValidateWorkItem
from tests.conftest import run_step


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "client_id": "C-1",
        "wiid": "WI-2",
        "fetched_type": "WI5",
        "fetched_status": "open",
        "fetched_hash": "same",
        "discovered_hash": "same",
    }
    state.update(overrides)
    return state


def test_validate_marks_success_without_failure_sentinel(example_config) -> None:
    transaction = run_step(
        ValidateWorkItem(name="validate", execution_order=1),
        state=_state(),
        config=example_config,
    )
    assert transaction.status is Status.SUCCESSFUL
    assert transaction.state["validated"] is True
    assert "validation_failed" not in transaction.state


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"client_id": ""}, "missing"),
        ({"fetched_type": "WI4"}, "Unsupported"),
        ({"fetched_status": "closed"}, "unexpected status 'closed'"),
        ({"fetched_status": "pending"}, "unexpected status 'pending'"),
        ({"fetched_hash": "new"}, "changed since discovery"),
    ],
)
def test_validate_business_failures_halt(overrides, message, example_config) -> None:
    transaction = run_step(
        ValidateWorkItem(name="validate", execution_order=1),
        state=_state(**overrides),
        config=example_config,
    )
    assert transaction.status is Status.FAILED
    exception = transaction.failed_steps()[0].exceptions[-1]
    assert isinstance(exception, BusinessException)
    assert exception.halts_remaining_steps is True
    assert message in str(exception)
