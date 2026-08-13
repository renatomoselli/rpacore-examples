# Git Repository Health Monitor

An RPA Core example that checks local Git repositories and writes a health report.

## Overview

This example demonstrates a repository-monitoring workflow:

1. **Check working tree** - Detect uncommitted files from `git status --porcelain`
2. **Capture recent commits** - Store the latest commit metadata
3. **Check remotes** - Record configured Git remotes
4. **Check stale branches** - Flag local branches older than the configured threshold
5. **Write repo report** - Classify each repository as healthy, degraded, or unhealthy
6. **Write summary** - Produce JSONL and summary JSON output for the whole run

The default config points at generated sample repositories. On the default config,
`main.py` creates deterministic `sample_repos/alpha` and `sample_repos/beta`
repositories before running the monitor.

## Architecture

```text
git_repo_health_monitor/
  main.py                    # Entry point and transaction orchestration
  config.toml                # Repo list, stale branch threshold, output paths
  create_sample_repos.py     # Creates deterministic sample repos for the default run
  steps/
    check_working_tree.py
    capture_recent_commits.py
    check_remotes.py
    check_stale_branches.py
    write_repo_report.py
    write_summary.py
  tests/
    unit/
    integration/

sample_repos/                # Created at runtime for the default config
rpacore.db                   # Transaction database created at runtime
health_report.jsonl          # Per-repo report rows created at runtime
health_report.summary.json   # Aggregate summary created at runtime
```

## Setup

```bash
cd examples/git_repo_health_monitor
python -m pip install -r requirements.txt
```

## Usage

```bash
cd examples/git_repo_health_monitor
python main.py
```

With the default sample repos:

- `alpha` is healthy
- `beta` is intentionally unhealthy because it has no remote, has uncommitted
  changes, and includes a stale branch

To monitor your own repositories, edit `config.toml` and replace the `repos`
list with local repository paths. Repository paths may point outside this
example directory; this is intentional because the monitor is meant to inspect
local Git checkouts wherever they live.

## Output

`health_report.jsonl` contains one JSON object per repository.

`health_report.summary.json` contains aggregate counts and embeds the repo
details used to build the summary.

Key fields include:

| Field | Description |
| --- | --- |
| `repository` | Absolute path to the checked repository |
| `repo_name` | Repository directory name |
| `health_status` | `healthy`, `degraded`, `unhealthy`, or `failed` |
| `failure_type` | `none`, `business`, or `system` |
| `classification` | Consumer-facing grouping such as `healthy`, `attention_needed`, or `technical_failure` |
| `persistence_status` | Whether that repository transaction was `saved` to the transaction database or `failed` during persistence |
| `uncommitted_changes` | Number of uncommitted files detected |
| `recent_commits` | Latest commit metadata captured from Git |
| `remotes` | Remote name to URL mapping |
| `stale_branches` | Local branches older than `stale_branch_days` |
| `last_commit` | Timestamp for the most recent captured commit |

Summary counters separate repository health from transaction failure semantics.
`business_violations` counts degraded and unhealthy repositories. `business_failed`
counts failed transactions whose root exception was a `BusinessException`.
`system_failed` counts failed transactions whose root exception was a
`SystemException`. The `failed` health status is reserved for transactions that
did not produce a normal repo health report, usually because an upstream step
failed before `WriteRepoReport` ran.

## RPA Core Behavior

Each repository is processed as its own transaction. The summary is written by a
separate transaction after all repositories are checked.

Repositories classified as degraded or unhealthy raise `BusinessException` in
the final per-repo step. The health report is written to `ctx.state` before that
exception is raised, so the summary can still include business-rule failures.

Technical failures such as missing Git commands or invalid repository paths are
reported as `SystemException` failures.

Transaction persistence uses `transaction_db_path` from `config.toml`. If a
per-repo transaction cannot be saved to the database, the monitor logs a warning,
marks that repo row with `persistence_status: "failed"` and `persistence_error`,
keeps the report data in memory, and continues. Rows saved successfully include
`persistence_status: "saved"`. If the summary transaction cannot be saved after
outputs are written, the output files are preserved and a warning is logged.

`WriteSummary` writes through temporary files and publishes the JSONL and summary
files separately. If JSONL publish succeeds but summary publish fails, the JSONL
file is preserved on disk as usable output, but the failed summary transaction
does not register successful artifacts.

## Configuration

```toml
max_retries = 2
log_level = "INFO"
transaction_db_path = "rpacore.db"
repos = [
    "sample_repos/alpha",
    "sample_repos/beta",
]
stale_branch_days = 30
output_file = "health_report.jsonl"
```

Use top-level `transaction_db_path` for RPA Core transaction persistence. The
entrypoint requires the committed `config.toml` beside `main.py`, regardless of
the caller's working directory. Configured `output_file` and
`transaction_db_path` values are resolved relative to this example directory
and must stay inside it. Repository paths are resolved separately and may point
to external local checkouts. The legacy top-level `db_path` key is rejected;
use `transaction_db_path`.

The local Git executable is required. The monitor uses local Git inspection
commands only; configured remote URLs are recorded but never contacted.

## Testing

```bash
cd examples/git_repo_health_monitor
python -m pytest tests/ -v
```

The tests cover individual Git-checking steps, summary generation, config
validation, and the main orchestration behavior.
