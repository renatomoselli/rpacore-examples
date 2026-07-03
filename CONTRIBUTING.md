# Contributing

Thanks for helping improve RPA Core Examples. This repository contains
consumer-facing automations that validate how RPA Core is used from the outside.

## Development Setup

Use Python 3.11 or newer. Each example owns its own dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
cd examples\json_event_log_processor
python -m pip install -r requirements.txt
python -m pytest tests
```

On POSIX shells, use `.venv/bin/python` instead of `.\.venv\Scripts\python`.

## Repository Boundaries

- Example automations belong under `examples/`.
- Framework code, framework packaging, and framework tests belong in the
  separate `rpacore` repository.
- Examples should import only supported public RPA Core APIs.
- Do not vendor framework source files into this repository.
- Do not add runtime AI behavior to example execution.

## Example Requirements

- Keep committed paths portable. Do not hardcode local checkout paths,
  drive-letter paths, home-directory paths, or user-specific machine paths.
- Use top-level `transaction_db_path`, not legacy `db_path`.
- Queue configs use `[queue].db_path` and `[queue].lease_timeout`.
- Put durable JSON-safe data in `ctx.state`.
- Put runtime handles, clients, pages, and open files in `ctx.resources`.
- Keep generated outputs, transaction databases, screenshots, and logs out of
  version control unless the file is intentional test fixture data.
- Pin the compatible `rpacore` release in each example's `requirements.txt`.

## Validation

Run the smallest relevant checks for the example you changed:

```powershell
python -m pytest tests
python main.py
```

Live examples that require browsers, desktop applications, network services, or
manual accounts should document the requirement and keep automated tests focused
on deterministic local behavior.

## Pull Requests

Use the pull request template. Include:

- the example or docs area changed
- the user-visible behavior being improved
- tests or live runs performed
- framework compatibility impact
- any required matching change in the `rpacore` repository

## Security

Do not report vulnerabilities in public issues with exploit details or sensitive
data. Follow [SECURITY.md](SECURITY.md).
