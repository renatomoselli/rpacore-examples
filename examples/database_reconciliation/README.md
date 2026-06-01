# Database Reconciliation

An RPA Core example that reconciles internal payment records against a bank statement export.

## Overview

This example demonstrates a finance-style batch automation:

1. **Load internal records** - Read ERP/accounting payments from CSV
2. **Load bank statement** - Read bank transactions from CSV and build a reference index
3. **Match transaction** - Find candidate bank entries for each internal payment
4. **Classify outcome** - Mark each payment as matched, missing, or amount mismatch
5. **Write report** - Produce a deterministic reconciliation report CSV

## Architecture

```text
sample_data/
  internal_payments.csv
  bank_statement.csv

main.py
  setup transaction loads both CSV files
  one RPA Core transaction per internal payment
  final report transaction writes output/reconciliation_report.csv

rpacore.db
  persisted transaction history
```

## Usage

```bash
cd examples/database_reconciliation
python main.py
```

The sample data includes 20 internal payments, 17 exact matches, 2 amount mismatches, and 1 missing bank entry.

## Output

`output/reconciliation_report.csv` contains:

| Field | Description |
|-------|-------------|
| `payment_id` | Internal payment ID |
| `date` | Internal payment date |
| `reference` | Shared payment/reference key |
| `vendor` | Internal vendor name |
| `internal_amount` | Amount from the internal system |
| `bank_amount` | Amount from the bank statement, if present |
| `bank_date` | Bank posted date, if present |
| `status` | `matched`, `amount_mismatch`, or `missing_from_bank` |
| `reason_code` | Empty for matched records, otherwise the discrepancy reason |

## RPA Core Behavior

Each internal payment is one transaction. Matched payments complete successfully.
Missing and mismatched payments raise `BusinessException`, so they are persisted as failed transactions with clear reason messages.

Unreadable or malformed source files raise `SystemException` during setup and stop the run.

## Testing

```bash
cd examples/database_reconciliation
python -m pytest tests/ -v
```
