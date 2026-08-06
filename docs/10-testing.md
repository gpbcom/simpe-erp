# 10 — Testing

Three campaigns, answering three different questions.

| Campaign | Question | Size |
|---|---|---|
| **pytest** — unit | Does each piece behave? | 938 test functions, hermetic |
| **pytest** — integration | Do the real services actually work? | 3, needing the stack |
| **Vitest** | Do the front-end's own units behave? | 8 |
| **Robot Framework** | Does the product work, in a browser, end to end? | 216 across 25 suites |

## Backend — unit

```sh
cd backend && uv run pytest
```

Hermetic by construction: in-memory SQLite, every outbound call stubbed, and
`-m 'not integration'` in the default `addopts`. Runs across all cores with a
60-second per-test timeout, which turns an unmocked database call into a fast
failure rather than a hung run.

Two fixtures carry most of it:

- `tests/conftest.py` — an **autouse** fixture neutralising `PostalAddress._geocode`.
  Without it most of the suite would hit public Nominatim, because the model
  geocodes during validation. A test that wants the real lookup opts out with
  the `geocoding` marker.
- `tests/storage/conftest.py` — a session on in-memory SQLite with
  `PRAGMA foreign_keys=ON`. That pragma is essential: SQLite ignores foreign
  keys by default, so without it the tests asserting a restricted delete is
  refused would pass for the wrong reason.

API tests build a throwaway FastAPI app and override the guard dependencies, so
an endpoint is exercised without mounting the authentication middleware.

`tests/storage/test_migrations.py` walks every revision against a temporary
database and diffs the result against `Base.metadata` — so ORM/migration drift
fails a test rather than a deployment.

`tests/api/test_exception_coverage.py` asserts every `MT*` family has a row in
the status table. Adding a service exception without registering it answers 500,
and this is what catches it.

## Backend — integration

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d
cd backend && uv run pytest -m integration
```

Marked, and excluded from the default run, so a laptop without the stack still
gets a green suite.

`tests/integration/test_email_delivery.py` is the one that matters: it sends
through the **real** `EmailService` over SMTP to Mailpit, then reads the message
back over Mailpit's REST API and opens the `.xlsx` attachment with openpyxl.

Every other email test stubs `_deliver` and inspects the `EmailMessage`. That
proves the message was *built* correctly and nothing about SMTP — the
connection, the STARTTLS decision, the login, the base64 encoding of a zip
archive. This is the only test that exercises those, and "openpyxl could read
it" is a stronger claim than "the bytes arrived".

The fixture empties the catcher before **and** after every test, which is what
makes it idempotent — and there is a test asserting the inbox is empty, as a
guard on the harness itself.

## Front-end — unit

```sh
cd frontend && npm run test
```

Vitest + Testing Library over the pieces worth isolating: the money and time
formatters, the initials fallback the map pins use, and `QuoteStatusChip` —
including that `pending-validation` really renders amber, because if it renders
like a draft the manager's queue is invisible in a list of ninety.

## GUI campaign

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d --build
pip install -r qa/requirements.txt && rfbrowser init
robot --outputdir qa/results qa/robot/suites
```

25 suites, 216 tests, driving Chromium through Playwright against the real API.

| Suite | Covers |
|---|---|
| 01 auth | Both roles; wrong password and unknown address answered identically |
| 02 hca account | The locked-field rule |
| 03 hca workspace | Planning, customers, quotes |
| 04 manager views | Quotes, workforce, map |
| **05 journey** | Submit → broker → worker → SSE → validate → author notified |
| 06 app shell | Navigation, language, theme, sign-out |
| 07 notifications | Badge, popover, centre, mark-all, empty state |
| 08 calendar | Three views, four controls, day bounds, drawer |
| 09 map | Pins, tooltips, windows, pin-count = list-count |
| 10 quote grids | Tabs, sort, page, conditional actions |
| 11 certifications | Full add → save → remove cycle |
| 12 routing & access | Guards reached by **typed URL**, rejected token |
| 13 portfolio | Cards, search, scoping asserted as a number |
| 14 account form | Every field, save, re-geocoding, locked fields preserved |
| 15 company registration | Signing an agency up from the public form |
| 16 quote creation | Writing a quote; the server prices what the screen sent |
| 17 team planning | The manager's who-and-when view: everybody, then one assistant, and that the narrowing really hides the others |
| 18 promotion | Granting an assistant an account, and taking it back |
| 19 planning computation | The solver run, end to end |
| 23 account by role | Every role gets an account page; employment locked for an assistant, editable for a manager; privileged fields refused |
| **24 customer file** | The beneficiary's file, ending an arrangement, and renewal |
| **20 quote editor** | Editing a quote, and who is allowed to — from both sides |
| 21 account credentials | The forced first change, and changing a password afterwards |
| **22 administration** | Navigation by role, the agency screen, and per-service pricing |
| 99 coverage | Merges the raw V8 output into one report |

Suite 05 is the one to read first: it is the only test that exercises the
publisher, the worker, the notification store and the event stream *together*.

### Locators

Every locator is a `data-testid`. A CSS class is Emotion's to rename on any MUI
upgrade and a visible string changes the moment somebody improves the French —
neither is a contract.

### Idempotency

**Every suite must be runnable twice against the same stack**, and CI proves it
by running the whole campaign a second time without resetting anything.

- Fixtures are created and removed **through the API**, never by clicking. A
  test that sets itself up through the UI cannot clean up when it fails halfway.
- Anything created carries a unique suffix, and teardown removes exactly what
  that run made **by identifier**, never by pattern.
- Seeded data is read-only. Where a suite must change something seeded, it
  snapshots the original and restores it in a teardown that runs even on failure.

### Coverage

The campaign collects real V8 coverage while it drives the browser; Vite's
source maps fold it onto the `.tsx` files, and suite 99 merges every suite's raw
output into `qa/results/coverage/index.html`. The threshold is in
`qa/coverage.config.json`.

`qa/COVERAGE.md` maps every route, component, control and state to the suite
covering it — that part is auditable by reading. The percentage requires
actually running the campaign.

## Type checking

```sh
cd backend && uv run ty check
```

**Not yet a blocking gate, and the reason is measured.** `ty` reports 137
diagnostics on `src/`: 80 are the documented `BaseMapper` generic contract —
it is generic over `ModelType`/`RowType` and reads `model.id` and
`row.created_at`, which the bounds cannot express — downgraded to warnings in
`pyproject.toml`. That leaves ~57 real findings, mostly the `Optional[str]`
identifier pattern.

`tests/` is excluded deliberately. Its job is to feed wrong types to validators
and assert they are refused; `Customer(first_name=123)` is the *point* of that
test. Checking it produced ~900 diagnostics all saying "this test does what it
was written to do", which buried the ones worth reading.

The CI job runs with `continue-on-error: true`. **Flip it once `ty check` is
clean.**

## Linting

```sh
cd backend  && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run lint && npx prettier --check "src/**/*.{ts,tsx}" && npm run typecheck
```

## CI

Ten jobs in `.github/workflows/ci.yml`, all parallel except the two needing
built artefacts. Beyond the obvious, two are worth knowing:

- **`openapi-drift`** regenerates the schema and fails if it differs from the
  committed copy. The front-end's types are hand-written; this is the other half
  of that trade.
- **`e2e-robot`** brings up the real stack, seeds it, runs the campaign, then
  **runs it again without resetting** — the only honest proof of idempotency —
  and dumps the container logs on failure.


## The manager-tooling suites

`16_quote_creation`, `17_team_planning` and `18_promotion` cover the screens
above. Two of them need care to stay idempotent, and say so in their own
documentation:

- **16** never validates a *seeded* quote. Validation is one-way, so consuming a
  seeded pending quote would leave the second run one short. It writes its own,
  validates that, and deletes what it wrote.
- **18** edits a seeded *account*, which no other suite does. The teardown
  demotes whoever was promoted rather than trusting the test to have got that
  far — a run that fails mid-promotion still leaves an assistant holding a
  manager's rights, and the next run would find the button gone.
- **17** writes nothing at all, so it is idempotent for free.
- **21** is the only suite that changes a *password*, which is the one edit
  that could stop the campaign running ever again — a seeded credential altered
  by a test that then failed before restoring it locks every later run out, and
  no teardown can recover what it no longer knows. So it creates its own
  assistant record and its own account, changes only that account's password,
  and deletes both by identifier afterwards. It buys the forced-first-change
  journey along the way: only a brand-new account can demonstrate it.
- **20** rewrites quotes, so it creates **two of its own** — one authored by the
  assistant, one by a manager. Two, not one, because the rule has two sides: the
  assistant's proves a manager may edit what they did not write, and the
  manager's proves an assistant may not. Editing a seeded quote instead would
  leave a changed fixture behind for every run after.

Two gotchas they encode, both worth not rediscovering:

- The quote list is cached for 30 seconds (`staleTime`). A test that changes a
  quote **over the API** and then reads the grid has to `Reload` first, or it
  renders the list as it was before the change.
- The role column comes from a *second* request, so the workforce grid is on
  screen before the roles are. Counting them immediately reports zero on a fast
  machine and one on a slow one; wait for the first chip.


## `19_planning_computation`

The one suite that is **not** idempotent in the ordinary sense, and says so. A
planning run writes interventions and re-running replaces them — that is what a
run *is*. What it guarantees instead is convergence: every run ends with one
succeeded run over the seeded week and the visits it placed, so the next run
starts where the last one finished. Its window is computed the way the seeder
computes its own rather than written down, so it follows the seeded data instead
of going stale the day after it was typed.
