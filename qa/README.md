# SimpleERP — GUI campaign

Drives the real application in a real browser, against the real API.

## Running it

The stack has to be up and seeded first:

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d --build
```

Then, once:

```sh
python3 -m venv qa/.venv
qa/.venv/bin/pip install -r qa/requirements.txt
qa/.venv/bin/rfbrowser init          # downloads the Playwright browsers
```

The environment lives in `qa/`, next to the code that uses it, rather than at
the repository root. A root `.venv` would be offered to the Python extension as
an interpreter for the backend, whose own environment is `backend/.venv` — and
the two share nothing: Robot Framework is deliberately kept out of the backend's
workspace so it is not shipped in the production image.

and thereafter:

```sh
qa/.venv/bin/robot --pythonpath qa/robot/resources --outputdir qa/results qa/robot/suites
```

## From VSCode

Both test suites appear in the Test Explorer with no further setup:

- **Unit tests** — pytest, discovered from `backend/` so it picks up
  `backend/pyproject.toml`. Integration tests are excluded by default (the
  `-m 'not integration'` in `addopts`); run them with the *Stack: up (dev)*
  task running and `-m integration` on the command line.
- **The GUI campaign** — Robot Framework, via the RobotCode extension, pointed
  at `qa/.venv` by `.vscode/settings.json`.

The one-off installation above is also available as the *QA: install Robot
Framework* task, alongside *QA: run the campaign* and a headed variant.

## Idempotency

**Every suite must be runnable twice in a row against the same stack**, and the
campaign is checked that way in CI. Two rules make it so:

1. Fixtures are created and removed through the **API**, never through the UI.
   A test that sets itself up by clicking is a test that fails to clean up when
   it fails half-way.
2. Anything a test creates carries a unique suffix from `Unique Suffix`, so two
   runs never collide on a reference or an email address — and the teardown
   removes exactly what that run made, rather than everything it finds.

The seeded data is treated as **read-only**. A suite that edited a seeded quote
would pass once and fail on the second run, which is precisely the failure this
rule exists to prevent.
