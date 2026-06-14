from __future__ import annotations

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.match_transaction import MatchTransaction


def _run(state):
    tx = Transaction(
        reference="payment-PAY-1",
        state=state,
        skills=[MatchTransaction(name="match_transaction", execution_order=1)],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=tx))
    return tx


def test_match_transaction_sets_candidates_for_reference():
    candidate = {"reference": "INV-1", "amount": "100.00"}
    tx = _run(
        {
            "current_payment": {"payment_id": "PAY-1", "reference": "INV-1"},
            "bank_by_reference": {"INV-1": [candidate]},
        }
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.state["bank_candidates"] == [candidate]


def test_match_transaction_fails_without_current_payment():
    tx = _run({"bank_by_reference": {}})

    assert tx.status == Status.FAILED
    assert "current_payment" in str(tx.failed_skills()[0].exceptions[-1])


def test_match_transaction_fails_without_bank_index():
    tx = _run({"current_payment": {"payment_id": "PAY-1", "reference": "INV-1"}})

    assert tx.status == Status.FAILED
    assert "bank_by_reference" in str(tx.failed_skills()[0].exceptions[-1])
