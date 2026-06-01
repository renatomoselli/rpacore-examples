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
inbox/                    # Input: JSON event log files
  ├── events_001.json     # Valid: 5 events
  ├── events_002.json     # Valid: 3 events
  ├── events_003.json     # Invalid: missing required fields
  ├── events_004.json     # Invalid: invalid event_type values
  └── events_005.json     # Malformed: not valid JSON

results/                  # Output: normalized JSONL files
  ├── events_001_cleaned.jsonl
  └── events_002_cleaned.jsonl

rpacore.db                   # SQLite database tracking transaction status
error_report.json         # Summary of failed transactions
```

## Prerequisites

- Python 3.9+
- `rpacore` package installed (`pip install rpacore`)

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

This will:
1. Process all `.json` files in the `inbox/` folder
2. Output normalized JSONL files to the `results/` folder
3. Write transaction history to `rpacore.db`
4. Generate `results/error_report.json` with failure details

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
  "failures": [
    {
      "transaction_id": 1,
      "transaction_reference": "json-file-events_003",
      "status": "FAILED",
      "retry_count": 0,
      "failed_skills": [
        {
          "skill_name": "validate_events",
          "skill_order": 2,
          "exception_type": "business",
          "message": "Event at index 1 missing required field: event_type"
        }
      ]
    }
  ]
}
```

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

## Skills

| Skill | Order | Description |
|-------|-------|-------------|
| `LoadJsonFile` | 1 | Read and parse JSON files |
| `ValidateEvents` | 2 | Validate event schema |
| `NormalizeEvents` | 3 | Standardize and enrich events |
| `WriteOutput` | 4 | Write normalized JSONL files |
| `WriteErrorReport` | 5 | Generate failure report |

## Key Design Decisions

1. **Validation short-circuit**: Unlike the `rest_api_batch` example where `BusinessException` doesn't stop execution, this pipeline uses a `validation_failed` flag to stop processing on validation errors.
2. **JSONL output**: Each normalized event is written as a single JSON line, suitable for streaming and log analysis tools.
3. **Per-file transactions**: Each input file is processed as a separate RPA Core transaction, enabling partial failure handling.
4. **UTC normalization**: All timestamps are normalized to UTC with timezone offset format.

## License

MIT
