# RPA Challenge Tests

This directory contains automated tests for the RPA Challenge automation.

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and configuration
├── unit/                    # Unit tests with mocked dependencies
│   ├── test_setup.py       # OpenChallengePage, DownloadInputData, StartChallenge
│   ├── test_row.py         # FillRow, SubmitRow
│   └── test_score.py       # RecordScore
└── integration/            # Integration tests with real browser
    └── test_full_workflow.py
```

## Running Tests

### Quick Setup

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Install Playwright browsers
playwright install
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

### Run Specific Test Categories

```bash
# Run smoke tests only (fast)
pytest -m smoke

# Run integration tests only (requires network)
pytest -m integration

# Run tests with verbose output and stack traces
pytest -v --tb=long
```

### Parallel Execution

```bash
# Run tests in parallel (faster)
pytest -n auto

# Run with specific workers
pytest -n 4
```

## Test Types

| Type | Description | Network Required | Speed |
|------|-------------|------------------|-------|
| Unit | Mock-based, tests individual skills | No | Fast |
| Integration | Real browser, tests full workflow | Yes | Slow |

## CI/CD Integration

Add to your CI pipeline:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pip install -r requirements-test.txt
    playwright install
    pytest --cov=. --cov-report=xml
```

## Notes

- Integration tests may be skipped in CI environments without network
- Unit tests are preferred for fast feedback in development
- Use `-m integration -n auto --timeout=300` for parallel integration tests with 5min timeout
