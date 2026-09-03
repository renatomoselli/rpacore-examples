# RPA Core examples

User-facing example automations built on top of RPA Core.

This repository is intentionally separate from the main RPA Core framework repo.
It exists to validate the real consumer workflow:

- install RPA Core as a package
- write custom steps in a separate project
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

The default branch targets the RPA Core release range declared by each
example's `requirements.txt`. For an older framework release, use the examples
tag that matches that release line.

Each production transaction declares a named `definition_identity` constant.
That token belongs to the automation definition, not to an individual run or
the RPA Core package version. Keep it stable across compatible fixes and Core
upgrades; change it only when an in-progress transaction must not resume under
the changed automation definition.

Most example folders include their own `requirements.txt`; those files pin the
compatible RPA Core release and any example-specific libraries. During release
rehearsal, install the freshly built local wheel from the exact framework commit
being validated before running the example requirements or validation script.

## Quick Start

From the `rpacore-examples` repository root, create and activate a virtual
environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
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

## Release Rehearsal

During RPA Core release rehearsal, this repository must be at the examples
commit recorded in the framework release manifest. Deterministic examples are
validated against the freshly built framework wheel, and the resulting
examples validation results are referenced by the framework release approval
record.

See the framework
[release rehearsal guide](https://github.com/renatomoselli/rpacore/tree/main/docs/release-rehearsal.md).

## Community and Support

- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Maintainers](MAINTAINERS.md)
- [Authors](AUTHORS.md)
- [Notice](NOTICE)

## Project Layout

Each example under `examples/` follows a consistent structure:

```text
examples/<name>/
  main.py              # Entry point - run with python main.py
  config.toml          # Workflow configuration
  steps/              # Individual step modules
    __init__.py
    <step_name>.py
  tests/
    unit/              # Unit tests per step
    integration/       # End-to-end workflow tests
```

## License

Apache 2.0. See [LICENSE](LICENSE).

