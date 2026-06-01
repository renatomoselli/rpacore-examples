# REST API Batch Processor

An RPA Core example that demonstrates batch processing of REST API records.

## Overview

This example fetches all posts from [JSONPlaceholder](https://jsonplaceholder.typicode.com/), enriches each with user data, validates the records, and writes the results to a JSONL output file.

It demonstrates:
- **Per-transaction processing**: Each post is processed as an independent transaction
- **Retry on transient failures**: The RPA Core Engine retries skills that raise `SystemException`
- **Business vs system exceptions**: Validation failures (`BusinessException`) are permanent; network errors (`SystemException`) are retried
- **Crash recovery**: Transaction state is persisted to SQLite after each transaction

## Prerequisites

- Python 3.11+
- `requests` library

## Setup

```bash
cd examples/rest_api_batch
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

This will:
1. Fetch all 100 posts from JSONPlaceholder
2. For each post, fetch the corresponding user, validate, enrich, and write to `output.jsonl`
3. Persist transaction state to `rpacore.db` for crash recovery

## Output

- `output.jsonl` — one JSON object per line, each containing post and enriched user data
- `rpacore.db` — SQLite database with transaction history

### Example output line:

```json
{"postId":1,"title":"sunt aut facere repellat provident occaecati excepturi optio reprehenderit","body":"quia et suscipit...","userId":1,"userName":"Leanne Graham","userEmail":"Sincere@april.biz","userCity":"Gwenborough"}
```

## Configuration

Edit `config.toml`:

```toml
max_retries = 2       # Number of retry attempts for transient failures
log_level = "INFO"     # Logging level
db_path = "rpacore.db"    # Transaction database path
output_file = "output.jsonl"  # Output JSONL file path
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Architecture

```
main.py              — Entry point, orchestrates setup + per-post transactions
skills/
  fetch_posts.py     — Fetches all posts from /posts
  fetch_user.py      — Fetches a single user from /users/{userId}
  validate_post.py   — Validates post has non-empty title and body
  enrich_record.py   — Merges post and user data
  write_output.py    — Appends enriched record to JSONL file
config.toml          — Configuration
requirements.txt     — Dependencies (requests)
```

## Skills

| Skill | Transaction | Execution Order | Purpose |
|-------|-----------|-----------------|---------|
| FetchPosts | Setup (runs once) | 1 | Fetch all posts from JSONPlaceholder |
| FetchUser | Per-post | 1 | Fetch user data for current post |
| ValidatePost | Per-post | 2 | Validate post has non-empty title and body |
| EnrichRecord | Per-post | 3 | Merge post and user data into enriched record |
| WriteOutput | Per-post | 4 | Append enriched record to JSONL output file |

## Exception Handling

- **BusinessException**: Raised when a post fails validation (empty title/body). This is a permanent failure — the post will not be retried.
- **SystemException**: Raised for network errors, HTTP errors, or file I/O errors. The Engine will retry up to `max_retries` times.

## License

This example is part of the RPA Core examples project.
