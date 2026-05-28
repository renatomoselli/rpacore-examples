from __future__ import annotations

from decimal import Decimal

from oref import Engine, ProcessContext, Status, Transaction

from skills.classify_outcome import ClassifyOutcome


def _run(payment, candidates):
    tx = Transaction(
        reference=f"payment-{payment['payment_id']}",
        skills=[ClassifyOutcome(name="classify_outcome", execution_order=1)],
    )
    data = {"current_payment": payment, "bank_candidates": candidates}
    Engine(max_retries=0).run(ProcessContext(transaction=tx, data=data))
    return tx, data


def test_classify_outcome_marks_exact_amount_match_successful():
    payment = {
        "payment_id": "PAY-1001",
        "date": "2024-04-01",
        "reference": "INV-1001",
        "amount": Decimal("1250.00"),
        "vendor": "Northwind Supplies",
    }
    candidate = {
        "posted_date": "2024-04-01",
        "reference": "INV-1001",
        "amount": Decimal("1250.00"),
        "description": "ACH Northwind Supplies",
    }

    tx, data = _run(payment, [candidate])

    assert tx.status == Status.SUCCESSFUL
    assert data["reconciliation_result"]["status"] == "matched"
    assert data["reconciliation_result"]["reason_code"] == ""


def test_classify_outcome_flags_missing_payment_as_business_exception():
    payment = {
        "payment_id": "PAY-1019",
        "date": "2024-04-10",
        "reference": "INV-1019",
        "amount": Decimal("1120.00"),
        "vendor": "Woodgrove Bank",
    }

    tx, data = _run(payment, [])

    assert tx.status == Status.FAILED
    assert data["reconciliation_result"]["status"] == "missing_from_bank"
    assert data["reconciliation_result"]["reason_code"] == "missing_from_bank"
    assert "missing from bank statement" in str(tx.failed_skills()[0].exceptions[-1])


def test_classify_outcome_flags_amount_mismatch_as_business_exception():
    payment = {
        "payment_id": "PAY-1006",
        "date": "2024-04-03",
        "reference": "INV-1006",
        "amount": Decimal("1575.30"),
        "vendor": "Wide World Importers",
    }
    candidate = {
        "posted_date": "2024-04-03",
        "reference": "INV-1006",
        "amount": Decimal("1570.30"),
        "description": "ACH Wide World Importers",
    }

    tx, data = _run(payment, [candidate])

    assert tx.status == Status.FAILED
    assert data["reconciliation_result"]["status"] == "amount_mismatch"
    assert data["reconciliation_result"]["bank_amount"] == Decimal("1570.30")


def test_classify_outcome_rejects_unexpected_bank_amount_type():
    payment = {
        "payment_id": "PAY-1006",
        "date": "2024-04-03",
        "reference": "INV-1006",
        "amount": Decimal("1575.30"),
        "vendor": "Wide World Importers",
    }
    candidate = {
        "posted_date": "2024-04-03",
        "reference": "INV-1006",
        "amount": "1575.30",
        "description": "ACH Wide World Importers",
    }

    tx, data = _run(payment, [candidate])

    assert tx.status == Status.FAILED
    assert "Bank candidate amount has unexpected type" in str(tx.failed_skills()[0].exceptions[-1])
    assert "reconciliation_result" not in data
