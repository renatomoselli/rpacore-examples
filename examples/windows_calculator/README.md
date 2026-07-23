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

Copy the immutable sample into the runtime inbox, then run the example:

```powershell
New-Item -ItemType Directory -Force input | Out-Null
Copy-Item samples\expr_example.csv input\expr_example.csv
windows-calculator  # or: python main.py
```

The queue provides at-least-once delivery; stable references prevent duplicate
enqueueing of the same inbox filename. Runtime files move to
`done/` on success or `failed/` on validation or expression failure, while the
tracked sample in `samples/` remains unchanged. Add CSVs with new filenames for
later runs; remove the local queue and transaction databases to reset demo state.
Results appear in `output/`.

The Calculator executable is discovered from Windows' `WINDIR`/`SystemRoot`
environment rather than a machine-specific drive path. Set the optional
`calculator_path` config key only when using a different executable.

## Architecture

```text
samples/
  expr_example.csv          <- immutable tracked sample

input/                      <- runtime inbox (created automatically)

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
Queue delivery counters are runner-owned terminal dispositions, including retry,
terminal-failure, lease-loss, and unknown-transition outcomes.

Configuration follows the current RPA Core API: top-level transaction
persistence uses `transaction_db_path`, and queue leases use
`[queue].lease_timeout` rather than the older queue claim-timeout key.
Configured data paths are resolved inside this example directory, and queued
source files are validated against `input/` before they are read or moved.
The committed `config.toml` is required beside `main.py`; an optional
`calculator_path` may point to an executable outside the project directory.

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
