# Project Context: rpacore-examples

Consumer-facing examples for the RPA Core Python workflow/skills framework.
Framework source is external; this repo contains example automations, not framework internals, framework tests, or packaging logic.

## Structure

```
examples/<name>/
  main.py              # Entry point — run with `cd examples/<name> && python main.py`
  config.toml          # Config: max_retries, log_level, transaction_db_path, plus example-specific keys
  skills/              # Skill modules (one file per skill)
    __init__.py        # Empty, or shared constants / re-exports
    <skill>.py         # class SkillName(Skill): def execute(self, ctx: ProcessContext)
  tests/
    unit/              # pytest unit tests
    integration/         # End-to-end via main()
```

## Conventions (across all examples)

- **Python header:** every `.py` file starts `from __future__ import annotations`
- **Config keys:** use top-level `transaction_db_path`, not legacy `db_path`. Queue configs use `[queue].db_path` and `[queue].lease_timeout`.
- **Config paths:** set `PROJECT_ROOT = Path(__file__).resolve().parent`; resolve relative config paths with `resolve_config_paths(config, keys, base_dir=PROJECT_ROOT, root=PROJECT_ROOT)`. Preserve intentional absolute paths in tests/callers.
- **Skills:** subclass `Skill`, implement `execute(self, ctx: ProcessContext)`. Read config via `ctx.require_config(key, type, action=self.name)`. Put durable JSON-safe data in `ctx.state`; put runtime handles/clients/pages/files in `ctx.resources`.
- **Transactions:** defined in `main.py` with explicit `execution_order` on skills. Run via `Engine(max_retries=N).run(ProcessContext(transaction=tx, config=config))`.
- **Exceptions:** `BusinessException` for expected rule failures; it marks the skill/transaction failed and only stops downstream skills with `stop=True`. Use `SystemException` for technical failures.
- **Artifacts:** generated files are recorded with `ctx.add_artifact(name, path, kind, metadata)`. Store paths and JSON-safe metadata, not file content.
- **Tests:** use helper functions (e.g. `_run_skill`, `_run`) that build a `Transaction` with `Engine(max_retries=0)` and assert on `tx.status` and `tx.state`.
