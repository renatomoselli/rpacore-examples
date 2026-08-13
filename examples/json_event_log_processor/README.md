# JSON Event Log Processor

An RPA Core example that processes JSON event log files through a batch pipeline.

## Overview

This example demonstrates processing JSON event logs through a 5-step pipeline:

1. **Load** — Read and parse JSON files from the inbox folder
2. **Validate** — Check events conform to the expected schema (required fields, valid event_type)
3. **Normalize** — Standardize timestamps to UTC, map event types to severity codes, enrich with metadata
4. **Output** — Write normalized events as JSONL (JSON Lines) to the results folder
5. **Error Report** — Generate a JSON summary of failed transactions for debugging

## Architecture

```
sample_data/              # Default committed input: JSON event log files
  ├── events_001.json     # Valid: 5 events
  ├── events_002.json     # Valid: 3 events
  ├── events_003.json     # Invalid: missing required fields
  ├── events_004.json     # Invalid: invalid event_type values
  └── events_005.json     # Malformed: not valid JSON

results/                  # Output: normalized JSONL files
  ├── events_001_cleaned.jsonl
  ├── events_002_cleaned.jsonl
  └── error_report.json   # Summary of failed transactions and persistence errors

rpacore.db                   # SQLite database tracking transaction status
```

## Prerequisites

- Python 3.12+
- RPA Core installed through `requirements.txt` (`rpacore>=0.3.0,<0.4.0`)

## Setup

```bash
# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the processor:

```bash
python main.py
```

The command loads the committed `config.toml` beside `main.py`, so it has the
same behavior when launched from this directory or a nested working directory.
The configured database, inbox, and results paths must remain under the
example directory.

This will:
1. Process all five committed `.json` files in `sample_data/`
2. Output normalized JSONL files to the `results/` folder
3. Write transaction history to `rpacore.db`
4. Generate `results/error_report.json` with failed transaction and persistence details

To process a different local directory, copy the sample data with `make sample`
and set `inbox_dir = "inbox"` in `config.toml`, or point `inbox_dir` at another
contained directory. The committed default stays reproducible for a fresh clone.

## Expected Behavior

### Successful Files

- `events_001.json` → `results/events_001_cleaned.jsonl` (5 normalized events)
- `events_002.json` → `results/events_002_cleaned.jsonl` (3 normalized events)

### Failed Files

- `events_003.json` → **FAILED** — missing required fields (event_id, event_type, timestamp, source)
- `events_004.json` → **FAILED** — invalid event_type values ("critical", "debug" not in allowed set)
- `events_005.json` → **FAILED** — malformed JSON

### Normalized Output Format

Each line in the JSONL output follows this schema:

```jsonl
{
  "event_id": "evt-001",
  "event_type": "info",
  "timestamp": "2024-01-15T08:30:00+00:00",
  "source": "auth-service",
  "severity": "INFO",
  "payload": {"message": "User login successful", ...},
  "processed_at": "2024-01-15T08:30:00.000000",
  "version": "1.0"
}
```

### Error Report Format

```json
{
  "total_transactions": 5,
  "successful": 2,
  "failed": 3,
  "unresolved": 0,
  "persistence_error_count": 0,
  "persistence_errors": [],
  "failures": [
    {
      "transaction_id": 1,
      "transaction_reference": "json-file-events_003",
      "status": "FAILED",
      "retry_count": 0,
      "outcome_category": "business_failed",
      "retry_disposition": "not_requested",
      "failure_code": "json_event_log.validation.invalid_event",
      "failed_steps": [
        {
          "step_name": "validate_events",
          "step_order": 2,
          "exception_type": "business",
          "message": "Event at index 1 missing required field: event_type"
        }
      ]
    }
  ]
}
```

`failed` counts transactions that reached the terminal `FAILED` status. `unresolved`
counts persisted transactions that are neither `SUCCESSFUL` nor `FAILED`. If a file
is processed but its transaction cannot be written to `rpacore.db`, the batch
continues and the persistence problem is listed in `persistence_errors`.

Each failure also includes the durable outcome category, the final retry
disposition, and an optional stable failure code. These are recorded by RPA
Core at the execution boundary; `retry_count` remains the number of retry
passes that actually ran, not a substitute for the final retry decision.

The error report queries the database by the current run's persisted `run_id` and
continues through every matching result page before loading failure details. It is
therefore scoped to the run even when more than 100 newer transactions from other
runs exist.

Both JSONL output and the error report publish atomically: an existing complete
file remains in place if creating, writing, syncing, or replacing the new file
fails.

## Event Schema

Events must conform to this schema:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string | Yes | Unique event identifier |
| `event_type` | string | Yes | One of: `info`, `warning`, `error` |
| `timestamp` | string | Yes | ISO 8601 timestamp (e.g., `2024-01-15T08:30:00Z`) |
| `source` | string | Yes | Service name that generated the event |
| `payload` | object | No | Optional event payload data |

## Testing

Run all tests:

```bash
cd examples/json_event_log_processor
python -m pytest tests/ -v
```

Run only unit tests:

```bash
python -m pytest tests/unit/ -v
```

Run only integration tests:

```bash
python -m pytest tests/integration/ -v
```

## Steps

| Step | Order | Description |
|-------|-------|-------------|
| `LoadJsonFile` | 1 | Read and parse JSON files |
| `ValidateEvents` | 2 | Validate event schema |
| `NormalizeEvents` | 3 | Standardize and enrich events |
| `WriteOutput` | 4 | Write normalized JSONL files |
| `WriteErrorReport` | 5 | Generate failure report |

## Key Design Decisions

1. **Validation short-circuit**: Unlike the `rest_api_batch` example where `BusinessException` doesn't stop execution, this pipeline raises validation errors with `halts_remaining_steps=True` so downstream steps do not run for invalid files.
2. **JSONL output**: Each normalized event is written as a single JSON line, suitable for streaming and log analysis tools.
3. **Per-file transactions**: Each input file is processed as a separate RPA Core transaction, enabling partial failure handling.
4. **Persistence error visibility**: Transaction-save failures are captured in the error report while the remaining files continue processing.
5. **UTC normalization**: All timestamps are normalized to UTC with timezone offset format.

## License

MIT
