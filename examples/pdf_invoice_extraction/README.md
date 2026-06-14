# PDF Invoice Extraction

Queue-driven PDF invoice extraction example using `SqliteQueue` and
`run_queue_loop`.

## Overview

This example discovers PDF invoice files in `sample_data/`, enqueues them
idempotently, processes each queued item through a five-skill pipeline, and
writes normalized records to CSV output.

## Pipeline

```text
scan_inbox -> open_pdf -> parse_invoice -> validate_invoice -> normalize_record -> write_output
```

`scan_inbox` is a setup function in `main.py`. The remaining steps are RPA Core
skills executed per queue item.

## RPA Core Features Shown

- `SqliteQueue.add_once()` prevents duplicate active PDF references.
- `run_queue_loop(..., transaction_db_path=...)` binds queue items to durable
  transactions for retry and resume behavior.
- Queue payload values are seeded into `ctx.state`.
- `BusinessException(stop=True)` stops downstream normalization and output for
  invalid invoices.
- `SystemException` marks unreadable or corrupt PDFs as retryable failures.
- `ctx.add_artifact()` records the output CSV and moved source PDF with invoice
  metadata.

## Usage

```bash
python main.py
```

On a fresh checkout, `main.py` generates demo invoices automatically when
`sample_data/` has no PDFs anywhere under it yet. A completed run leaves PDFs in
`sample_data/done/`, so later runs do not regenerate duplicates automatically.
You can regenerate the demo inputs explicitly with:

```bash
python generate_sample_data.py
```

Successful invoices are appended to `results/output.csv` and moved to
`sample_data/done/`. Invalid or unreadable PDFs remain in `sample_data/` so the
queue outcome and transaction history can be inspected.

## Configuration

Top-level keys:

| Key | Default | Description |
| --- | --- | --- |
| `max_retries` | `2` | Engine retries for retryable system failures |
| `log_level` | `"INFO"` | Logging level |
| `transaction_db_path` | `"rpacore.db"` | Durable transaction database |
| `sample_data_dir` | `"sample_data"` | Directory containing input PDFs |
| `results_dir` | `"results"` | Directory for output artifacts |
| `output_csv` | `"results/output.csv"` | CSV output path |
| `max_pages` | `100` | Maximum pages to extract per PDF |

Queue keys under `[queue]`:

| Key | Default | Description |
| --- | --- | --- |
| `db_path` | `"queue.db"` | SQLite queue database |
| `lease_timeout` | `30` | Seconds before an abandoned claim can be retried |
| `max_retries` | `0` | Queue retry budget after engine retries are exhausted |

## Output

`results/output.csv` contains:

| Column | Description |
| --- | --- |
| `invoice_number` | Uppercase invoice number |
| `date` | Invoice date in ISO 8601 format |
| `vendor` | Uppercase vendor name |
| `line_items_count` | Number of parsed line items |
| `subtotal` | Sum of line items, formatted to two decimals |
| `total` | Invoice total, formatted to two decimals |
| `currency` | Detected currency code |

Each successful transaction also records:

- `invoice_csv`: CSV output artifact with invoice number, vendor, and source file metadata.
- `source_pdf`: moved source PDF artifact when the file exists locally.

## Testing

```bash
python -m pytest tests
python -m pytest tests/unit
python -m pytest tests/integration
```

## Project Structure

```text
examples/pdf_invoice_extraction/
  main.py
  config.toml
  requirements.txt
  generate_sample_data.py
  README.md
  sample_data/
    done/
    failed/
  skills/
    __init__.py
    open_pdf.py
    parse_invoice.py
    validate_invoice.py
    normalize_record.py
    write_output.py
  tests/
    unit/
    integration/
```

## Known Limitations

- The CSV writer assumes single-worker processing. Concurrent workers can race
  on duplicate detection and header creation.
- Failed PDFs are left in `sample_data/`; this keeps the example focused on
  queue outcomes rather than file-disposition callbacks.
