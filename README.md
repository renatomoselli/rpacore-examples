# RPA Core examples

User-facing example automations built on top of RPA Core.

This repository is intentionally separate from the main RPA Core framework repo.
It exists to validate the real consumer workflow:

- install RPA Core as a package
- write custom skills in a separate project
- run automations without importing framework source files directly

## What Belongs Here

- complete example automations
- beginner-friendly starter projects
- examples that show recommended project structure
- docs that explain how to use RPA Core from the outside

## What Does Not Belong Here

- framework internals
- framework tests
- packaging logic for RPA Core itself
- examples that only exist to support the RPA Core test suite

## Quick Start

From a sibling checkout of the RPA Core framework repo, build a wheel:

```powershell
cd ..\rpacore
.venv\Scripts\python.exe -m build
```

From this repo, create and activate a virtual environment:

```powershell
cd ..\rpacore-examples
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the latest built wheel:

```powershell
pip install ..\rpacore\dist\rpacore-0.1.0-py3-none-any.whl
```

Run an example from its own directory:

```powershell
cd examples\json_event_log_processor
python main.py
```

Most examples include tests:

```powershell
python -m pytest tests
```

## Project Layout

Each example under `examples/` follows a consistent structure:

```text
examples/<name>/
  main.py              # Entry point - run with python main.py
  config.toml          # Workflow configuration
  skills/              # Individual skill modules
    __init__.py
    <skill_name>.py
  tests/
    unit/              # Unit tests per skill
    integration/       # End-to-end workflow tests
```

