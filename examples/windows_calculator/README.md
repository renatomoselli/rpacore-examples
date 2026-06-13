# Windows Calculator

Run arithmetic checks through the Windows Calculator app using RPA Core skills and pywinauto.

## Requirements

- Windows with the built-in Calculator app available
- Python 3.11+
- UI automation access for the current desktop session
- RPA Core installed (`pip install rpacore`)

## Usage

Install the example:

```powershell
pip install -e .
```

Run the example with the built-in sample:

```powershell
windows-calculator
```

Or run directly:

```powershell
python main.py
```

The queue processes each CSV in `input/` exactly once. A sample file (`input/expr_example.csv`) is included — edit it or add more CSVs to `input/` and re-run; new files are picked up automatically. Results appear in `output/` and processed files move to `done/` (success) or `failed/` (validation or expression failure).

## Architecture

```text
input/
  expr_example.csv          <- sample CSV (edit or replace)

skills/
  load_expressions.py       <- Skill 1: parse and validate CSV
  open_calculator.py        <- Skill 2: launch Calculator
  process_expressions.py    <- Skill 3: type + compare
  close_calculator.py       <- Skill 4: cleanup
  write_report.py           <- Skill 5: write results CSV artifact
  move_file.py              <- Skill 6: move successful files to done/

output/
  expressions_results.csv   <- results written here

done/                       <- processed files moved here
failed/                     <- failed files moved here
```

Each CSV file becomes one RPA Core transaction with 6 skills executed in sequence.
The queue ensures exactly-once processing per file.

Configuration follows the current RPA Core API: top-level transaction
persistence uses `transaction_db_path`, and queue leases use
`[queue].lease_timeout` rather than the older queue claim-timeout key.

## CSV Schema

| Field | Type | Rule |
|-------|------|------|
| `expression` | string | Arithmetic expression (digits, +, -, *, /, parentheses) |
| `expected_result` | string | Expected calculator display value |

## Testing

```bash
cd examples/windows_calculator
python -m pytest tests/ -v
```

Unit tests mock the Calculator interactor. Integration tests verify the
full RPA Core skill pipeline with mocked automation.
