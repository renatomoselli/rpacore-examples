# Checkpoint / Resume Demo

An RPA Core example that demonstrates transaction checkpoint and resume capability.

## Overview

In long-running or unreliable automation workflows, a failure partway through a
transaction can waste all previously completed work. RPA Core's
**checkpoint/resume** feature solves this by persisting transaction state to a
database after each run. When a transaction fails, `resume_transaction()` loads
the persisted state, marks already-successful skills as skipped, resets failed
skills to pending, and lets the engine continue from where it left off.

This example uses a two-skill pipeline to demonstrate the pattern:

The example intentionally retains its explicit `Engine.run()` checkpoints and
`resume_transaction()` call: recovery sequencing, skill reattachment, and
history inspection are the behavior being demonstrated.

1. **SaveState** — Increments a counter, writes a JSON checkpoint file, and
   records an artifact. This skill always succeeds.
2. **FailTask** — On the first run, raises a `SystemException` to simulate an
   interruption. On resume (when `fail_on_first_run` is toggled to `false`), it
   increments the counter again and marks the transaction as complete.

## Architecture

```
checkpoint_resume/
  main.py              # Entry point: runs first pass, resumes if failed
  config.toml          # Config (fail_on_first_run, max_retries, etc.)
  skills/
    __init__.py
    save_state.py      # Skill A: always succeeds, writes durable state
    fail_task.py       # Skill B: fails on first run, succeeds on resume
  reports/             # Separate immutable failed and resumed report records
  tests/
    unit/              # Unit tests for individual skills
    integration/       # Integration test for the full workflow
  rpacore.db           # SQLite database (created at runtime)
  checkpoint.json      # Checkpoint artifact (created by SaveState)
```

## Expected Output

### First Run (Partial Failure)

```
=== Starting first run ===
First run status: FAILED
  transaction_started -  (order None)
  skill_started - save_state (order 1)
  skill_succeeded - save_state (order 1)
  skill_started - fail_task (order 2)
  skill_failed - fail_task (order 2)
  transaction_completed -  (order None)
```

Skill A (save_state) succeeds and its state is persisted. Skill B (fail_task)
raises `SystemException`, causing the transaction to fail. The checkpoint
database now contains the partially-completed transaction.

The example also writes an immutable failed report record under `reports/`.
After resume it writes a second successful record with the same transaction ID;
the failed record is never overwritten.

### Resume (Completion)

```
Resuming transaction...
Resume status: SUCCESSFUL
  transaction_started -  (order None)
  skill_started - save_state (order 1)
  skill_succeeded - save_state (order 1)
  skill_started - fail_task (order 2)
  skill_failed - fail_task (order 2)
  transaction_resumed -  (order None)
  skill_started - fail_task (order 2)
  skill_succeeded - fail_task (order 2)
  transaction_completed -  (order None)
```

Notice that **save_state is NOT re-run** — its successful status is preserved
from the persisted transaction. Only fail_task executes again, now succeeding
because `fail_on_first_run` is `false`.

## Prerequisites

- Python 3.11+
- RPA Core installed through `requirements.txt` (`rpacore>=0.3.0,<0.4.0`)

## Setup

```bash
# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the example:

```bash
python main.py
```

This will:

1. Execute the first run with strict engine checkpoints to `rpacore.db`
2. Preserve save_state's successful status and state after fail_task fails
3. Resume the transaction (fail_task runs again and succeeds)
4. Print a summary showing the final counter value and resume flag

## Key Concepts

### Durable State

`ctx.state` is a JSON-safe dict that survives across runs. The `SaveState` skill
writes a counter dict to `ctx.state["counter"]`. On resume, this state is
restored from the database so the counter retains its value.

### Config and Published Files

`main.py` always loads the committed `config.toml` beside the entry point and
resolves the database and checkpoint destinations under that project root.
The checkpoint file is published atomically before state and artifact metadata
are updated. If persistence fails immediately after `SaveState` succeeds, the
new checkpoint is removed; later or resumed persistence failures retain the
last checkpoint as recovery evidence.

Each failed-and-resumed demonstration creates two immutable JSON report-v1
records in `reports/`. They preserve the original failure, the final outcome,
canonical retry/failure information, and the full resume history separately.

### Artifact Recording

Skills can record artifacts via `ctx.add_artifact(name, path, kind, metadata)`.
Artifacts are file paths and JSON-safe metadata. The checkpoint file is recorded
as an artifact so it can be tracked in the transaction audit trail.

### Resume Logic

`resume_transaction()` loads the persisted transaction from the database, matches
skills by `(name, execution_order)`, and:

- Preserves skills that were `SUCCESSFUL` (they are not re-executed)
- Resets skills that were `FAILED` to `PENDING` (they are re-executed)
- Appends a `TRANSACTION_RESUMED` history event
- Sets the transaction status to `PENDING` so it can be re-run

## Testing

Run all tests:

```bash
cd examples/checkpoint_resume
pip install -r requirements-test.txt
python -m pytest tests/ -v
```

Run only unit tests:

```bash
python -m pytest tests/unit/ -v
```

Run only integration tests:

```bash
python -m pytest tests/integration/ -v
```

## License

MIT
