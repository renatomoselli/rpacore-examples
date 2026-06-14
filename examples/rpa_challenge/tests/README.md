# RPA Challenge Tests

This directory contains deterministic tests for the RPA Challenge automation.

## Test Structure

```text
tests/
|-- conftest.py
|-- unit/
|   |-- test_main.py
|   |-- test_setup.py
|   |-- test_row.py
|   `-- test_score.py
`-- integration/
    `-- test_full_workflow.py
```

## Running Tests

```bash
pip install -r requirements-test.txt

# Unit tests with mocked Playwright/page objects
pytest tests/unit/

# Mocked workflow-level tests
pytest tests/integration/

# Full deterministic suite
pytest tests/unit/ tests/integration/
```

## Test Types

| Type | Description | Network Required |
|------|-------------|------------------|
| Unit | Individual skills and helpers with mocks | No |
| Integration | Multi-skill workflow behavior with mocked browser/downloads | No |
| Live | Actual browser run against rpachallenge.com via `python main.py` | Yes |

Run the live validation only when Playwright browsers are installed and the public site is stable:

```bash
playwright install chromium
python main.py
```
