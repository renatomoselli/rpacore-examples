from __future__ import annotations

from rpacore import Engine, ProcessContext, Status, Transaction

from skills.classify_outcome import ClassifyOutcome


def _run(state):
    tx = Transaction(
        reference="payment-PAY-1",
        state=state,
        skills=[ClassifyOutcome(name="classify_outcome", execution_order=1)],
    )
    Engine(max_retries=0).run(ProcessContext(transaction=tx))
    return tx


def test_classify_outcome_marks_exact_amount_match_successful():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1001",
                "date": "2024-04-01",
                "reference": "INV-1001",
                "amount": "1250.00",
                "vendor": "Northwind Supplies",
            },
            "bank_candidates": [
                {
                    "posted_date": "2024-04-01",
                    "reference": "INV-1001",
                    "amount": "1250.00",
                    "description": "ACH Northwind Supplies",
                }
            ],
        }
    )

    assert tx.status == Status.SUCCESSFUL
    assert tx.state["reconciliation_result"]["status"] == "matched"
    assert tx.state["reconciliation_result"]["reason_code"] == ""


def test_classify_outcome_flags_missing_payment_as_business_exception():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1019",
                "date": "2024-04-10",
                "reference": "INV-1019",
                "amount": "1120.00",
                "vendor": "Woodgrove Bank",
            },
            "bank_candidates": [],
        }
    )

    assert tx.status == Status.FAILED
    assert tx.state["reconciliation_result"]["status"] == "missing_from_bank"
    assert tx.state["reconciliation_result"]["reason_code"] == "missing_from_bank"
    assert "missing from bank statement" in str(tx.failed_skills()[0].exceptions[-1])


def test_classify_outcome_flags_amount_mismatch_as_business_exception():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1006",
                "date": "2024-04-03",
                "reference": "INV-1006",
                "amount": "1575.30",
                "vendor": "Wide World Importers",
            },
            "bank_candidates": [
                {
                    "posted_date": "2024-04-03",
                    "reference": "INV-1006",
                    "amount": "1570.30",
                    "description": "ACH Wide World Importers",
                }
            ],
        }
    )

    assert tx.status == Status.FAILED
    assert tx.state["reconciliation_result"]["status"] == "amount_mismatch"
    assert tx.state["reconciliation_result"]["bank_amount"] == "1570.30"


def test_classify_outcome_reports_closest_mismatch_candidate():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1006",
                "date": "2024-04-03",
                "reference": "INV-1006",
                "amount": "1575.30",
                "vendor": "Wide World Importers",
            },
            "bank_candidates": [
                {
                    "posted_date": "2024-04-03",
                    "reference": "INV-1006",
                    "amount": "1200.00",
                    "description": "ACH Wide World Importers partial",
                },
                {
                    "posted_date": "2024-04-03",
                    "reference": "INV-1006",
                    "amount": "1570.30",
                    "description": "ACH Wide World Importers",
                },
            ],
        }
    )

    assert tx.status == Status.FAILED
    assert tx.state["reconciliation_result"]["status"] == "amount_mismatch"
    assert tx.state["reconciliation_result"]["bank_amount"] == "1570.30"


def test_classify_outcome_rejects_non_string_payment_amount():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1001",
                "date": "2024-04-01",
                "reference": "INV-1001",
                "amount": 1250,
                "vendor": "Northwind Supplies",
            },
            "bank_candidates": [
                {
                    "posted_date": "2024-04-01",
                    "reference": "INV-1001",
                    "amount": "1250.00",
                    "description": "ACH Northwind Supplies",
                }
            ],
        }
    )

    assert tx.status == Status.FAILED
    assert tx.state["reconciliation_result"]["status"] == "type_error"
    assert "Current payment amount must be str, got 1250" in str(
        tx.failed_skills()[0].exceptions[-1]
    )


def test_classify_outcome_rejects_non_string_bank_amount():
    tx = _run(
        {
            "current_payment": {
                "payment_id": "PAY-1001",
                "date": "2024-04-01",
                "reference": "INV-1001",
                "amount": "1250.00",
                "vendor": "Northwind Supplies",
            },
            "bank_candidates": [
                {
                    "posted_date": "2024-04-01",
                    "reference": "INV-1001",
                    "amount": 1250,
                    "description": "ACH Northwind Supplies",
                }
            ],
        }
    )

    assert tx.status == Status.FAILED
    assert tx.state["reconciliation_result"]["status"] == "type_error"
    assert tx.state["reconciliation_result"]["bank_amount"] == 1250
    assert "Bank candidate amount must be str, got 1250" in str(
        tx.failed_skills()[0].exceptions[-1]
    )


def test_result_helper_uses_defaults_for_missing_bank_entry():
    from skills.classify_outcome import _result

    result = _result(
        {
            "payment_id": "PAY-1",
            "date": "2024-04-01",
            "reference": "INV-1",
            "amount": "100.00",
            "vendor": "Vendor A",
        },
        "missing_from_bank",
        None,
    )

    assert result == {
        "payment_id": "PAY-1",
        "date": "2024-04-01",
        "reference": "INV-1",
        "vendor": "Vendor A",
        "internal_amount": "100.00",
        "bank_amount": "",
        "bank_date": "",
        "status": "missing_from_bank",
        "reason_code": "missing_from_bank",
    }
