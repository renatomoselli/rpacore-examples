# RPA Challenge Web Automation

Public benchmark challenge demonstrating robust label-based browser automation.

## What It Does

Downloads employee data from Excel (10 rows), then fills a web form with randomized field positions.

**Key learning:** Uses `get_by_label()` selectors to handle randomized field positions that would break position-based automation.

## Quick Start

```bash
# Install runtime dependencies
pip install -r requirements.txt
playwright install chromium

# Run the automation
cd examples/rpa_challenge
python main.py
```

Expected output:
```
Setup successful
fill_row: success
submit_row: success
... (10 rows)
Final score: XX
```

## Verify Setup

```bash
# Check dependencies are installed
pip list | grep -E "playwright|openpyxl"

# Verify browser installation
playwright install chromium

# Test browser is working
playwright-cli open https://www.rpachallenge.com --headed
```

---

## Dependencies

### Runtime

| Package | Purpose |
|---------|---------|
| `playwright` | Browser automation for web form filling |
| `openpyxl` | Parsing the challenge.xlsx input file |

### Dev Tools (Optional)

| Tool | Purpose |
|------|---------|
| `playwright-cli` | Selector debugging and verification |

---

## Architecture

### Transactions

```
setup:    [OpenChallengePage] → [DownloadInputData] → [StartChallenge]

row×10:   [FillRow] → [SubmitRow]

score:    [RecordScore]
```

### Skills

| Skill | Purpose |
|-------|---------|
| `OpenChallengePage` | Launch browser, navigate to challenge site |
| `DownloadInputData` | Download & parse challenge.xlsx |
| `StartChallenge` | Click Start button to begin |
| `FillRow` | Fill 7 form fields (label-based) |
| `SubmitRow` | Submit each row |
| `RecordScore` | Read final score and close browser |

---

## External Dependencies

| Item | Reason |
|------|--------|
| [RPACHallenge](https://www.rpachallenge.com/) | Challenge website (internet required) |

---

## Verification

```bash
# 1. Run automation
python main.py

# 2. Check transaction log
sqlite3 oref.db "SELECT reference, status FROM transactions ORDER BY rowid;"

# 3. Expected: 12 successful transactions
```

## Risks & Maintenance

| Risk | Mitigation |
|------|-----------|
| Field labels change | Use `playwright-cli snapshot` to verify |
| Download URL changes | Graceful error handling in `DownloadInputData` |

---

## Running Tests

### Setup

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Install Playwright browsers (if not already done)
playwright install
```

### Run Tests

```bash
# All tests
pytest

# Unit tests only (fast, no network)
pytest tests/unit/

# Integration tests only (requires network)
pytest tests/integration/

# With coverage
pytest --cov=. --cov-report=html
```

See `tests/README.md` for full documentation.

---

## Related

- [O REF framework](https://github.com/oref-org/oref)
- [RPACHallenge](https://www.rpachallenge.com/)

## Improvements Implemented

- ✅ Config validation in `main.py`
- ✅ Retry logic for page navigation failures
- ✅ Input data schema validation
- ✅ Configurable XLSX URL
- ✅ Screenshot on failure enabled
- ✅ Comprehensive test suite (unit + integration)
