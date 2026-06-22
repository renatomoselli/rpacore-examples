# REST API Batch Processor

An RPA Core example that demonstrates batch processing of REST API records.

## Overview

This example processes deterministic REST-shaped fixture data by default, enriches each post with user data, validates the records, and writes the valid results to a JSONL output file. The skills can also run against [JSONPlaceholder](https://jsonplaceholder.typicode.com/) by changing `api_mode` to `"live"`.

It demonstrates:
- **Per-transaction processing**: Each post is processed as an independent transaction
- **Retry on transient failures**: The RPA Core Engine retries skills that raise `SystemException`
- **Business vs system exceptions**: Validation failures (`BusinessException`) are permanent; HTTP/network errors (`SystemException`) are retried
- **Artifact reporting**: Successful output writes attach the JSONL path to the transaction audit trail
- **Audit persistence**: Transaction state is persisted to SQLite after each transaction

## Prerequisites

- Python 3.11+
- RPA Core 0.1.0 and Requests 2.33+ (installed from `requirements.txt`)

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
1. Load deterministic fixture posts without using the network
2. Validate each post before fetching/enriching user data
3. Skip invalid records via `BusinessException(stop=True)`
4. Write valid enriched records to `output.jsonl`
5. Persist transaction state to `rpacore.db` as an audit trail

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
transaction_db_path = "rpacore.db"  # Transaction database path
output_file = "output.jsonl"        # Output JSONL file path
api_mode = "fixture"                # fixture = no network, live = JSONPlaceholder
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
| FetchPosts | Setup (runs once) | 1 | Fetch all posts from fixture data or JSONPlaceholder |
| ValidatePost | Per-post | 1 | Validate post has non-empty title, body, and userId |
| FetchUser | Per-post | 2 | Fetch user data for current post |
| EnrichRecord | Per-post | 3 | Merge post and user data into enriched record |
| WriteOutput | Per-post | 4 | Append enriched record to JSONL output file |

## Exception Handling

- **BusinessException**: Raised for validation failures and permanent API responses (4xx except 408/429), so they are not retried. Invalid posts are persisted as failed and omitted; a permanent setup failure aborts the batch.
- **SystemException**: Raised for network errors, retryable HTTP responses (408/429/5xx), or file I/O errors. The Engine retries up to `max_retries` times; if retries are exhausted, the batch aborts and restores the previous run's output.
- **Run boundaries**: Each successful run replaces `output.jsonl`, while `rpacore.db` retains the transaction history across runs. Output deduplication protects skill retries within the current run rather than serving as cross-run recovery.
- **Aborted runs**: If a later post exhausts retries, the previous JSONL output is restored. Transactions already attempted in the aborted run remain in SQLite as execution history even though that run's JSONL is not published.

## License

This example is part of the RPA Core examples project.
