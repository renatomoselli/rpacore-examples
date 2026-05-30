# Windows Calculator

Run arithmetic checks through the Windows Calculator app using OREF skills and pywinauto.

## Requirements

- Windows with the built-in Calculator app available
- Python 3.11+
- UI automation access for the current desktop session
- OREF installed (`pip install oref`)

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
  open_calculator.py        <- Skill 1: launch Calculator
  load_expressions.py       <- Skill 2: parse CSV
  process_expressions.py    <- Skill 3: type + compare
  write_report.py           <- Skill 4: write results CSV
  move_file.py              <- Skill 5: move successful files to done/
  close_calculator.py       <- Skill 6: cleanup

output/
  expressions_results.csv   <- results written here

done/                       <- processed files moved here
failed/                     <- failed files moved here
```

Each CSV file becomes one OREF transaction with 6 skills executed in sequence.
The queue ensures exactly-once processing per file.

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
full OREF skill pipeline with mocked automation.
