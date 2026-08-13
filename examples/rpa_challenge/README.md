# RPA Challenge Web Automation

Public benchmark challenge demonstrating browser automation with RPA Core transaction state, runtime resources, retries, and transaction persistence.

## What It Does

Downloads the challenge workbook, opens the RPA Challenge website, starts the challenge, submits each employee row through a randomized web form, and records the final score.

**Key learning:** Playwright browser/page handles live in `ctx.resources`, while durable row data and final score live in `ctx.state`. The form fill step builds a label-to-input map from the live DOM and dispatches Angular-compatible input events so randomized field positions do not break the automation.

## Quick Start

```bash
cd examples/rpa_challenge

# Install runtime dependencies
pip install -r requirements.txt
playwright install chromium

# Run the automation
python main.py
```

Expected output:

```text
INFO | transaction_started | Transaction started | transaction_reference=rpa-challenge-setup
INFO | step_started | Step started | step_name=open_challenge_page
INFO | step_completed | Step completed | step_name=open_challenge_page step_status=successful
INFO | step_started | Step started | step_name=download_input_data
INFO | step_completed | Step completed | step_name=download_input_data step_status=successful
INFO | step_started | Step started | step_name=start_challenge
INFO | step_completed | Step completed | step_name=start_challenge step_status=successful
INFO | transaction_completed | Transaction completed | transaction_reference=rpa-challenge-setup transaction_status=successful
INFO | transaction_started | Transaction started | transaction_reference=rpa-row-...
INFO | step_started | Step started | step_name=fill_row
INFO | step_completed | Step completed | step_name=fill_row step_status=successful
INFO | step_started | Step started | step_name=submit_row
INFO | step_completed | Step completed | step_name=submit_row step_status=successful
INFO | transaction_completed | Transaction completed | transaction_reference=rpa-row-... transaction_status=successful
... (10 rows)
INFO | transaction_started | Transaction started | transaction_reference=rpa-challenge-score
INFO | step_started | Step started | step_name=record_score
INFO | step_completed | Step completed | step_name=record_score step_status=successful
INFO | transaction_completed | Transaction completed | transaction_reference=rpa-challenge-score transaction_status=successful
Final score: 100%
```

## Verify Setup

```bash
# Check dependencies are installed
pip list | grep -E "rpacore|playwright|openpyxl"

# Verify browser installation
playwright install chromium
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `rpacore` | Transaction engine, steps, state/resources, persistence |
| `playwright` | Browser automation |
| `openpyxl` | Parsing the challenge workbook |

## Architecture

### Transactions

```text
setup:  [OpenChallengePage] -> [DownloadInputData] -> [StartChallenge]
row x10:[FillRow] -> [SubmitRow]
score:  [RecordScore]
```

Each run submits all rows in one active browser session. Row transactions are persisted for traceability, but row-level resume is intentionally disabled because the challenge site's progress is not restored across fresh sessions. If the browser crashes or the challenge page is closed mid-run, restart the example to begin a fresh challenge session.

### Steps

| Step | Purpose |
|-------|---------|
| `OpenChallengePage` | Launch Playwright, navigate to the challenge site, and store runtime handles in `ctx.resources` |
| `DownloadInputData` | Download and parse the workbook, then store JSON-safe rows in `ctx.state` |
| `StartChallenge` | Click the Start button and wait for the randomized form |
| `FillRow` | Map visible labels to input IDs and fill one row |
| `SubmitRow` | Submit one row and wait for the next round or results page |
| `RecordScore` | Parse and persist the final score in `ctx.state` |

## External Dependencies

| Item | Reason |
|------|--------|
| [RPACHallenge](https://www.rpachallenge.com/) | Challenge website and workbook download |

## Verification

```bash
# Deterministic tests with mocked browser/network dependencies
pytest tests/unit/
pytest tests/integration/

# Live browser run against the public website
python main.py

# Optional transaction log check
sqlite3 rpacore.db "SELECT reference, status FROM transactions ORDER BY rowid;"
```

The live run should create 12 successful transactions: one setup transaction, ten row transactions, and one score transaction.

## Running Tests

```bash
pip install -r requirements-test.txt

# Mocked tests, no live browser/site dependency
pytest tests/unit/
pytest tests/integration/

# Optional live validation is the actual example run
playwright install chromium
python main.py
```

See `tests/README.md` for the test layout.

## Configuration

`main.py` requires the committed `config.toml` beside it, regardless of the
caller’s working directory. `transaction_db_path` and an enabled
`screenshot_dir` are resolved relative to this example and must remain inside
it. Browser settings, timeouts, and workbook download options are validated as
configuration values; URL/host, workbook-schema, browser, and DOM behavior
remain explicit runtime checks.

The setup, each non-idempotent row, and score capture remain separate
transactions sharing Playwright resources. Persistence is traceability only;
on any abort, restart the challenge from a fresh browser session. Cleanup is
unconditional after the workflow exits.

## Related

- [RPA Core](https://github.com/renatomoselli/rpacore)
- [RPACHallenge](https://www.rpachallenge.com/)
