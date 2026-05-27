# File Inbox Processor

An OREF example that uses the queue path to process branch CSV reports dropped into an inbox folder.

## Overview

This example demonstrates a file-system automation with one queue item per input file:

1. **Scan** - Add each `.csv` file in `inbox/` to `SqliteQueue`
2. **Read** - Parse the branch report CSV
3. **Validate** - Check schema, types, and business rules
4. **Compute** - Add `revenue_per_headcount`
5. **Append** - Write the clean record to a consolidated master CSV
6. **Move** - Move the source file to `done/` or `failed/`

## Architecture

```text
inbox/
  branch_101_2024-03-01.csv
  branch_205_2024-03-01.csv
  branch_invalid_headcount.csv

queue.db
  pending -> in_progress -> successful/failed

output/
  master_consolidated.csv

done/
failed/
```

## Usage

```bash
cd examples/file_inbox_processor
python main.py
```

Successful files are appended to `output/master_consolidated.csv` and moved to `done/`.
Files with business-rule violations are moved to `failed/`.

## CSV Schema

| Field | Type | Rule |
|-------|------|------|
| `branch_id` | integer | Must be positive |
| `date` | ISO date | Example: `2024-03-01` |
| `revenue` | decimal | Must be greater than or equal to zero |
| `headcount` | integer | Must be greater than zero |

## Queue Behavior

`scan_inbox` enqueues files as `QueueItem` payloads with `file_path`.
It skips files that already have pending or in-progress queue items, so a
restart after scanning does not create duplicate active work.
`run_queue_loop` claims each item atomically, runs the OREF transaction, and marks the queue item successful or failed.

The OREF engine retries retryable `SystemException` failures within the transaction according to `max_retries`. Queue-level retries are disabled in this example because source files are moved after a terminal queue outcome.

Invalid business data raises `BusinessException`, skips downstream processing, and is not retried. The master CSV includes `source_file` and will not append the same source file twice.

## Testing

```bash
cd examples/file_inbox_processor
python -m pytest tests/ -v
```
