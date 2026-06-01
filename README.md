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

From the RPA Core repo, build a wheel:

```powershell
cd d:\repos\oref
.venv\Scripts\python.exe -m build
```

From this repo, create and activate a virtual environment:

```powershell
cd d:\repos\oref-examples
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the latest built wheel:

```powershell
pip install d:\repos\oref\dist\rpacore-0.1.0-py3-none-any.whl
```

Run the starter example:

```powershell
python .\main.py
```

## Project Layout

```text
oref-examples/
  config.toml
  main.py
  skills/
    __init__.py
    greet_user.py
```

## Starter Example

The included example builds a transaction with three user-space skills:

1. validate the input
2. write a greeting file
3. confirm the file contents

This keeps the example small while still showing the RPA Core execution pattern.
