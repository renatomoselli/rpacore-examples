# Maintainers

## Current Maintainer

- Renato Moselli

## Ownership Areas

- Example automations: `examples/`
- Repository documentation: `README.md`, `CONTRIBUTING.md`, `SUPPORT.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`
- Legal and attribution: `LICENSE`, `NOTICE`, `AUTHORS.md`
- Agent and contribution guidance: `AGENTS.md`, `.github/`
- Framework compatibility notes: `README.md#framework-compatibility` and
  per-example `requirements.txt`

## Review Expectations

Example behavior changes need focused tests. Public documentation changes should
match the current example workflow. Changes that depend on unpublished framework
behavior must either include the matching framework commit context or wait for a
compatible RPA Core release.

Before release rehearsal, maintainers should confirm that this repository points
to the intended compatible RPA Core version and that deterministic examples pass
against the framework wheel being validated.
