# Project Context: rpacore-examples

Consumer-facing examples for the RPA Core Python workflow/steps framework.
Framework source is external; this repo contains example automations, not framework internals, framework tests, or packaging logic.

## Structure

```
examples/<name>/
  main.py              # Entry point — run with `cd examples/<name> && python main.py`
  config.toml          # Config: max_retries, log_level, transaction_db_path, plus example-specific keys
  steps/              # Step modules (one file per step)
    __init__.py        # Empty, or shared constants / re-exports
    <step>.py         # class StepName(Step): def execute(self, ctx: ProcessContext)
  tests/
    unit/              # pytest unit tests
    integration/         # End-to-end via main()
```

## Conventions (across all examples)

- **Python header:** every `.py` file starts `from __future__ import annotations`
- **Config keys:** use top-level `transaction_db_path` for transaction persistence. Queue configs use `[queue].db_path` and `[queue].lease_timeout`.
- **Config paths:** committed examples, docs, configs, and test literals must be portable across machines. Prefer relative config paths resolved from `PROJECT_ROOT = Path(__file__).resolve().parent` with `resolve_config_paths(config, keys, base_dir=PROJECT_ROOT, root=PROJECT_ROOT)`. Do not hardcode local absolute paths such as drive-letter paths, home-directory paths, or user-specific checkout paths. Tests may use `tmp_path` or other generated temporary paths only when validating path handling.
- **Steps:** subclass `Step`, implement `execute(self, ctx: ProcessContext)`. Read config via `ctx.require_config(key, type, action=self.name)`. Put durable JSON-safe data in `ctx.state`; put runtime handles/clients/pages/files in `ctx.resources`.
- **Transactions:** defined in `main.py` with explicit `execution_order` on steps. Ordinary single transactions use `execute_transaction(tx, config=config, engine=Engine(max_retries=N), transaction_db_path=...)`; advanced examples retain their explicit Engine, checkpoint, queue, or resource-lifecycle paths where they own those boundaries.
- **Exceptions:** `BusinessException` for expected rule failures; it marks the step/transaction failed and only stops downstream steps with `halts_remaining_steps=True`. Use `SystemException` for technical failures.
- **Artifacts:** generated files are recorded with `ctx.add_artifact(name, path, kind, metadata)`. Store paths and JSON-safe metadata, not file content.
- **Tests:** use helper functions (e.g. `_run_step`, `_run`) that build a `Transaction` with `Engine(max_retries=0)` and assert on `tx.status` and `tx.state`.
