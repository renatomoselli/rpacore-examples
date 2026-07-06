# ACME Work Items

This capstone example discovers open remote ACME work items across every table
page and mirrors them into a durable local queue. It then uses an authenticated
Playwright session to fetch, validate, hash, update, and close eligible WI5
items. It demonstrates RPA Core queue binding and resume,
`resource_scope`, credential providers, strict checkpoints, replay-safe remote
operations, artifacts, reports, and optional notifications in one workflow.

The required tests are fully local: a stateful HTTP server models ACME while real
Chromium automation exercises login redirects, cookies, selectors, session
expiry, updates, closes, and screenshots. The external ACME site is never a
default test dependency.

## Workflow

Each discovered open item is seeded with exactly two JSON-safe fields:
`work_item_id` and its discovery-time concurrency fingerprint. Item URLs are
always derived from the trusted `base_url`; a queue payload cannot supply one.
`SqliteQueue.add_once()` suppresses another pending or in-progress item with the
same reference. A reference that has already reached a terminal completed or
failed status may be discovered and intentionally seeded by a later invocation.
Discovery follows the ACME table pagination and de-duplicates item IDs before
seeding. Non-WI5 and malformed items are expected business failures; they are
recorded without retrying and are not modified remotely.

The transaction order is explicit:

1. `FetchWorkItem` reads a fresh remote snapshot.
2. `ValidateWorkItem` rejects bad, stale, unsupported, or unexpectedly closed
   items with `BusinessException(stop=True)`.
3. `ComputeSecurityHash` computes `SHA1(clientID + WIID)` and checkpoints the
   deterministic update intent.
4. `UpdateWorkItem` writes the deterministic hash comment and verifies the
   exact stored value. Repeating the write converges to the same comment.
5. `CloseWorkItem` closes and verifies the item, or recognizes an authorized
   already-closed replay. It records a screenshot artifact.

Durable, JSON-safe values live in `ctx.state`. The browser, page, cookies, and
credential provider live only in `ctx.resources`/`ctx.credentials`. Every
browser skill re-establishes authentication and navigates independently, so a
persisted transaction can resume under a fresh process and browser.

## Setup

From this directory:

```powershell
python -m pip install -r requirements.txt
python -m pip install "rpacore[keyring]>=0.1.0,<0.2.0"
python -m playwright install chromium
```

The committed configuration uses the operating-system keyring. Store the two
named credentials without adding their values to TOML:

```powershell
python -c "import keyring; keyring.set_password('rpacore', 'acme_username', 'your-user')"
python -c "import keyring; keyring.set_password('rpacore', 'acme_password', 'your-password')"
python main.py
```

To use process-local environment variables instead, set
`credential_provider = "env"` in `config.toml`, then run:

```powershell
$env:RPACORE_CRED_ACME_USERNAME = "your-user"
$env:RPACORE_CRED_ACME_PASSWORD = "your-password"
python main.py
```

RPA Core reads these secrets through the provider; it does not store or
provision them. Keyring writes above are performed by the external `keyring`
package and operating-system backend.

## Outputs and resilience

Item transactions and strict skill checkpoints are stored in `rpacore.db`; the
queue is stored separately in `queue.db`. A run-level summary is written
atomically under `reports/` and persisted as its own transaction. Item-close
screenshots are stored under `screenshots/`. All paths are resolved relative to
this example directory.

Each summary describes queue claims handled by that invocation, not the
cumulative contents of ACME or the local output directories. Each successful
item record references one screenshot artifact. Screenshot names are keyed by
work-item ID, so a verified replay replaces that item's existing file; the
directory may also contain screenshots from earlier runs.

`update_applied`, `updated_hash`, `closed_hash`, and `idempotency_outcome` are
durable audit checkpoints, not downstream control flags. In particular, a
failed screenshot can produce a failed transaction whose idempotency outcome is
still `closed`: the remote close is irreversible and must remain visible even
when optional artifact capture fails.

The update and close skills are deliberately idempotent. A process may stop
after the remote side effect but before its checkpoint. On retry, the update may
re-submit the same deterministic comment and verify it again. The persisted
close intent lets the close step recognize the matching already-completed item
without issuing another status transition.

Because terminal queue references may be seeded again, a later run can revisit
remote items that remain open after a business rejection. This makes validation
outcomes visible on every scan. Successfully closed items normally disappear
from discovery. A resumed transaction that already has durable close intent can
still use the verified already-closed replay path.

Notifications use RPA Core's existing `[notification.email]` and
`[notification.webhook]` configuration. No notification section is committed,
so the default run sends nothing.

## Tests

Install test requirements, then run from the repository root:

```powershell
python -m pip install -r examples/acme_work_items/requirements-test.txt
pytest examples/acme_work_items/tests/unit -q
pytest examples/acme_work_items/tests/integration -m "integration and not live" -q
pytest examples/acme_work_items/tests -m "not live" -q
```

The live smoke test is explicitly gated and may need selector updates if the
external ACME site changes:

```powershell
$env:RPACORE_CRED_ACME_USERNAME = "your-user"
$env:RPACORE_CRED_ACME_PASSWORD = "your-password"
$env:RUN_ACME_LIVE = "1"
pytest examples/acme_work_items/tests/live -m live -q
```

The smoke test uses the environment provider and performs login plus paginated
discovery only; it does not update or close remote items. The local suite is the
deterministic acceptance surface; external site availability, anti-bot
behavior, and selector drift are not release gates.
