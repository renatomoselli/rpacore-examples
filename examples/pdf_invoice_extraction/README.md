# PDF Invoice Extraction

Queue-driven PDF invoice extraction example using `SqliteQueue` + `run_queue_loop` to demonstrate RPA Core's defining architectural feature.

## Overview

This example discovers PDF invoice files in a `sample_data/` folder, processes them through a 5-skill pipeline, and writes normalized records to CSV output.

### Pipeline

```
scan_inbox → open_pdf → parse_invoice → validate_invoice → normalize_record → write_output
```

### Queue-Driven Architecture

1. **Setup phase**: `scan_inbox` discovers PDF files in `sample_data/` and enqueues each as a `QueueItem`
2. **Processing phase**: `run_queue_loop()` claims items one at a time, running each through the 5-skill pipeline
3. **Outcome**: Successful PDFs are moved to `sample_data/done/`

### Exception Handling

- **`SystemException`** (unreadable PDF, file I/O errors): retried up to `max_retries`
- **`BusinessException`** (validation failure): tracked, not retried — validation failures are permanent

## Prerequisites

```bash
pip install -r requirements.txt
```

- `pdfplumber` — PDF text extraction
- `reportlab` — sample PDF generation (optional; minimal fallback available)

## Usage

```bash
# 1. Generate sample data (requires reportlab for proper PDFs)
python generate_sample_data.py

# 2. Run the queue-driven pipeline
python main.py
```

## Configuration

| Key             | Default        | Description                          |
|-----------------|----------------|--------------------------------------|
| `max_retries`   | `2`            | Max retry attempts for transient errors |
| `log_level`     | `"INFO"`       | Logging level                        |
| `db_path`       | `"queue.db"`   | SQLite queue database path           |
| `sample_data_dir`| `"sample_data"` | Directory containing PDF invoices    |
| `results_dir`   | `"results"`    | Directory for CSV output             |
| `output_csv`    | `"results/output.csv"` | Output CSV file path          |
| `max_pages`     | `100`          | Maximum pages to process per PDF     |

## Output

After processing, `results/output.csv` contains:

| Column           | Description                          |
|------------------|--------------------------------------|
| `invoice_number` | Invoice number (uppercase)           |
| `date`           | Invoice date (ISO 8601)              |
| `vendor`         | Vendor name (uppercase)              |
| `line_items_count`| Number of line items               |
| `subtotal`       | Sum of line items (2 decimal places) |
| `total`          | Invoice total (2 decimal places)     |
| `currency`       | Detected currency code               |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v
```

## Project Structure

```
examples/pdf_invoice_extraction/
├── main.py                          # Queue orchestration entry point
├── config.toml                      # Per-example configuration
├── requirements.txt                 # Example-specific dependencies
├── generate_sample_data.py          # PDF fixture generation script
├── README.md                        # This file
├── sample_data/                     # PDF invoices (generated)
│   ├── invoice_001.pdf              # Valid invoice
│   ├── invoice_002.pdf              # Valid invoice
│   ├── ...
│   ├── done/                        # Successfully processed PDFs
│   └── failed/                      # Failed PDFs
├── skills/
│   ├── __init__.py
│   ├── scan_inbox.py                # Queue population
│   ├── open_pdf.py                  # PDF text extraction
│   ├── parse_invoice.py             # Invoice parsing
│   ├── validate_invoice.py          # Business rule validation
│   ├── normalize_record.py          # Data normalization
│   └── write_output.py              # CSV output + file move
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared fixtures
    ├── unit/
    │   ├── __init__.py
    │   ├── test_open_pdf.py
    │   ├── test_parse_invoice.py
    │   ├── test_validate_invoice.py
    │   ├── test_normalize_record.py
    │   ├── test_write_output.py
    │   ├── test_scan_inbox.py
    │   └── test_main.py
    └── integration/
        ├── __init__.py
        └── test_full_workflow.py
```

## Known Limitations

- **Single-worker CSV safety**: The `os.path.exists` header check is racy under concurrent workers. This example assumes single-worker operation.
- **Failed PDF auto-disposition**: Failed PDFs remain in `sample_data/` and will be re-queued on the next run. This requires a `run_queue_loop` callback or post-processing step to fix.
