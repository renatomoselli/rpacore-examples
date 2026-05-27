# Windows Calculator

Run arithmetic checks through the Windows Calculator app with pywinauto.

## Requirements

- Windows with the built-in Calculator app available
- Python 3.11+
- UI automation access for the current desktop session

This example is intentionally Windows-only. The unit tests mock the Calculator
automation boundary, but the CLI requires an interactive Windows desktop.

## Usage

Install the example:

```powershell
pip install -e .
```

Prepare a CSV file with these columns:

```csv
expression,expected_result
2+2,4
5*3,15
```

Run the batch:

```powershell
windows-calculator-test expressions.csv --output results.csv
```

Use `--fail-fast` to stop on the first failed expression and `--verbose` for
progress logging.
