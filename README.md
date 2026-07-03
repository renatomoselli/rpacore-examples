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

## Framework Compatibility

These examples target RPA Core `0.1.0`.

Most example folders include their own `requirements.txt`; those files pin the
compatible RPA Core release and any example-specific libraries. During release
rehearsal, install the freshly built local wheel from the exact framework commit
being validated before running the example requirements or validation script.
After RPA Core is public, use the released package version.

## Quick Start

From the `rpacore-examples` repository root, create and activate a virtual
environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the released package:

```powershell
python -m pip install "rpacore==0.1.0"
```

Or, during release rehearsal, build and install a local wheel from a sibling
framework checkout:

```powershell
cd ..\rpacore
.venv\Scripts\python.exe -m build
cd ..\rpacore-examples
python -m pip install ..\rpacore\dist\rpacore-0.1.0-py3-none-any.whl
```

Run an example from its own directory:

```powershell
cd examples\json_event_log_processor
python -m pip install -r requirements.txt
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

