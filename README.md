<p align="center">
  <!--
    Two variants behind a <picture>, because a README is read on both themes and
    a single ink cannot serve both. The mark itself — teal roof, heart, amber
    hands — is the same in each; only the wordmark's colour changes.
  -->
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-light.svg">
    <img src="docs/assets/logo-light.svg" alt="SimpleERP" width="300">
  </picture>
</p>

<p align="center">
  <strong>Quoting, workforce and intervention planning for a French home-care agency.</strong>
</p>

<p align="center">
  <a href="#what-it-does">What it does</a> ·
  <a href="#overall-architecture">Architecture</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#getting-it-running">Getting started</a> ·
  <a href="#docker">Docker</a> ·
  <a href="docs/README.md">Documentation</a>
</p>

---

## What it does

An agency quotes a family for care at home, a manager approves the price, and
the accepted work becomes a week of visits — who goes where, in what order, with
travel time and a lunch break accounted for. `SimpleERP` runs all three of those,
and the workforce and customer records behind them.

**For a home-care assistant**

- Their own record: contact details and address they may change; contract type
  and qualifications shown but locked, because those are a manager's decision.
- Their week as a calendar, computed from the accepted quotes.
- The customers they serve — not the agency's whole book.
- Quotes they have written, and a button that submits one for validation.

**For a manager or administrator**

- Every quote, with a validation queue: an assistant's submission waits here
  until somebody who sets prices agrees to it.
- The workforce, searchable, with the qualification editor.
- A map of every planned intervention over a configurable window, each pin being
  the assistant's photograph, each tooltip naming the customer.
- A notification centre, fed over the broker and pushed live over SSE.

## Overall architecture

Three application processes and three stores. The API and the worker run the
**same image** with different entry points — one image built two ways cannot
drift the way two Dockerfiles do.

```
                     ┌──────────────┐
   browser ────────▶ │  React SPA   │ ─────────┐
                     └──────────────┘          │  REST + SSE
                                               ▼
   ┌──────────┐  events  ┌──────────────┐  ┌────────┐
   │  worker  │ ◀──────▶ │  RabbitMQ    │◀─│  API   │
   │ solver + │          └──────────────┘  └────────┘
   │ notifier │                                │
   └──────────┘                                │
        │                                      │
        └──────────▶ PostgreSQL ◀──────────────┘
                     MinIO (photographs)
```

| Process | Does |
|---|---|
| **api** | Serves HTTP, holds the SSE connections, runs the migrations on boot |
| **worker** | Consumes the broker: runs the CP-SAT solves, writes notifications, sends email |
| **frontend** | Vite dev server, or nginx serving a built bundle and proxying `/api` |

### Inside the backend

A `uv` workspace of six members with a strict, one-directional dependency graph.
Nothing points back up it.

```
models  ←  storage  ←  service  ←  api
                          ↑
                          ├──  worker
                          └──  seed
```

`models` holds the domain and configuration and imports nothing first-party.
`storage` owns the tables, mappers and repositories — and never commits, because
the session it is handed already belongs to a transaction. `service` holds the
business logic and raises its own `MT*` exceptions rather than HTTP ones. `api`
translates those exceptions to statuses, once, and its endpoints contain no
business logic.

The **worker deliberately does not depend on `api`**: a background consumer that
pulled in FastAPI to read one YAML file would make the graph a ring.

### Two flows worth knowing

**A request** passes CORS → authentication → transaction → router → service →
repository. The order is load-bearing at both ends: CORS outermost so a rejected
credential still carries its headers, and the transaction innermost so it commits
*before* the response is written.

**An event** is published by the API and consumed by the worker. A publish that
fails never fails the request that caused it — a quote is submitted whether or
not the broker was reachable, because the manager's queue is a database query
rather than a message.

→ [docs/01 — Architecture](docs/01-architecture.md)

## Requirements

**To run it**, nothing but a container runtime:

| | |
|---|---|
| Docker Engine | 24 or newer |
| Docker Compose | v2 (`docker compose`, not `docker-compose`) |
| Memory | ~4 GB free — the solver and the broker are the hungry parts |
| Ports | 5173, 8000, 5432, 5672, 15672, 9000, 9001, 1025, 8025 |

The development overlay publishes every one of those ports so you can reach the
database and the broker directly. If something already holds one, either stop it
or drop that mapping from `docker-compose.dev.yaml`.

**To work on the code**, a toolchain per language — none of it needed if you
only run the stack:

| | | |
|---|---|---|
| Backend | Python **3.14** and [`uv`](https://docs.astral.sh/uv/) | `uv sync` installs the rest |
| Front-end | Node **20** | `.nvmrc` pins it; `npm ci` installs the rest |
| GUI campaign | Python 3.9+ and Playwright browsers | `pip install -r qa/requirements.txt && rfbrowser init` |

The pinned versions live in `backend/.python-version` and `frontend/.nvmrc`, and
CI reads both from those files rather than repeating them.

**Outbound network** is needed in two places, and only two. Nominatim is called
when an address is geocoded — which happens during model validation, so it fires
when a customer or an assistant is created, and never when one is read. The
seeder supplies coordinates precisely so it does not call it forty times. The
other is the image and package registries, at build time.

## Getting it running

```sh
cp .env.example .env
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

That brings up PostgreSQL, MinIO, RabbitMQ, the API, the worker, Mailpit and the
Vite dev server, runs the migrations, and seeds a working agency — 12 assistants,
40 customers, a service catalog and 54 quotes spread across every status.

Wait for `Bucket SimpleERP is ready.` and the seeder's credential block; the first
build takes a few minutes, and afterwards a start is seconds.

| | |
|---|---|
| Application | <http://localhost:5173> |
| API and its docs | <http://localhost:8000> · <http://localhost:8000/docs> |
| Caught email | <http://localhost:8025> |
| Broker management | <http://localhost:15672> — `simple_erp` / `simple_erp_dev` |
| Object store console | <http://localhost:9001> |

Sign in with any of the seeded accounts, all sharing the password
`simple-erp-demo-2026`:

| Role | Address | Lands on |
|---|---|---|
| Administrator | `admin@simple-erp.fr` | The quote screen |
| Manager | `manager@simple-erp.fr` | The quote screen |
| Assistant | `luc.martin@simple-erp.fr` | Their own planning |

Every seeded assistant signs in as `firstname.lastname@simple-erp.fr`.

## Docker

Three compose files. **The base is never run alone** — it describes what the
application *is*, and an overlay says how you want to run it.

| File | Adds |
|---|---|
| `docker-compose.yaml` | The services themselves: postgres, minio, minio-init, rabbitmq, backend, worker, frontend |
| `docker-compose.dev.yaml` | Source bind-mounts, live reload, every port published, Mailpit, the seeder |
| `docker-compose.prod.yaml` | Restart policies, resource limits, two workers, nginx, **mandatory secrets** |

Because two `-f` flags on every command gets tedious, export them once per shell:

```sh
export COMPOSE_FILE=docker-compose.yaml:docker-compose.dev.yaml
```

Every command below assumes that. Without it, spell both files out.

### Day to day

```sh
docker compose up -d                  # start, in the background
docker compose up --build             # rebuild first — after a dependency change
docker compose ps                     # what is running, and is it healthy
docker compose logs -f backend        # follow one service
docker compose logs -f backend worker # …or several
docker compose stop                   # stop, keeping the data
docker compose down                   # stop and remove the containers
```

Application source is **bind-mounted** in development: editing a `.py` reloads
uvicorn, editing a `.tsx` hot-reloads Vite. You only need `--build` when a
dependency changes — `pyproject.toml`, `uv.lock`, `package.json` — or when the
Dockerfile does.

### Starting a slice of it

The dependency graph is declared, so naming one service starts what it needs:

```sh
docker compose up -d backend          # …and postgres, minio, rabbitmq
docker compose up -d frontend         # …and the whole chain behind it
docker compose up -d postgres rabbitmq   # the stores alone, to run the app on the host
```

### Running things inside the stack

```sh
docker compose exec backend uv run pytest          # the test suite
docker compose exec backend alembic -c conf/alembic.ini current
docker compose exec backend alembic -c conf/alembic.ini upgrade head
docker compose exec backend bash                   # a shell in the API container
docker compose exec postgres psql -U simple_erp simple_erp # a database prompt

docker compose run --rm seed                       # re-run the seeder (idempotent)
```

The seeder writes nothing on a second run — every identifier is derived from a
natural key, so it upserts. Running it again is always safe.

### Starting over

```sh
DEV="-f docker-compose.yaml -f docker-compose.dev.yaml"
docker compose $DEV down -v --remove-orphans   # containers AND volumes: a clean database
docker compose $DEV up --build                 # rebuild and reseed from nothing
```

`-v` destroys `postgres-data`, `minio-data` and `rabbitmq-data`. In development
that is the fastest way back to a known state; anywhere else it is data loss.

**Use the same `-f` files to go down as you did to come up.** `mailpit` and
`seed` are defined only in the dev overlay, so a bare `docker compose down`
leaves them behind attached to the network it has just deleted — and the next
`up` fails with `network <id> not found`, naming the network rather than the two
containers that are really the problem.

### Rebuilding one image

```sh
docker compose build backend          # backend and worker share this image
docker compose build --no-cache frontend
docker compose up -d --force-recreate backend
```

The **worker runs the same image as the API** with a different entry point, so
`build backend` rebuilds both. That is deliberate: one image built two ways
cannot drift the way two Dockerfiles do.

### When something will not start

```sh
docker compose ps                     # look for unhealthy or exited
docker compose logs backend | tail -50
docker compose logs minio-init        # bucket creation — photographs and map pins
docker compose logs seed              # the credential block prints here
```

| Symptom | Usually |
|---|---|
| `backend` restarts in a loop | Migrations could not run — read its logs; check `POSTGRES_PASSWORD` matches |
| Photographs and map pins are broken | `minio-init` did not complete; re-run `docker compose up minio-init` |
| No notifications arrive | `worker` is down, or RabbitMQ never went healthy — it takes ~20 s on a cold start |
| Login rejects the seeded accounts | The seeder did not run: `docker compose run --rm seed` |
| A port is already in use | Something else holds 5432, 8000 or 5173; stop it, or drop that port from the dev overlay |
| `network <id> not found` on `up` | A previous `down` used a different `-f` set — see **Starting over** |
| `password authentication failed for user "simple_erp"` | A volume from before the rename — see below |

### Upgrading a stack created before the SimpleERP rename

The application was called `rt-erp`, and its database user, broker user and
bucket were named after it. If your volumes were created before the rename, the
first thing you will see is:

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "simple_erp"
```

**`POSTGRES_USER`, `RABBITMQ_DEFAULT_USER` and `MINIO_ROOT_USER` are read only
when the store initialises itself.** Changing them in compose does nothing to a
volume that already exists — the database still holds `rt_erp` while the
application now connects as `simple_erp`. Postgres fails first because the
backend reaches it first; the broker and the object store would fail next.

For a development stack, throw the volumes away — the data is seeded, and
reseeding takes seconds:

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml down -v --remove-orphans
docker network rm rt-erp_rt-erp                       # the network named after the old product
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

**Tear down with the same `-f` files you brought it up with.** `mailpit` and
`seed` exist only in the dev overlay, so a plain `docker compose down -v` does
not know about them: it deletes the network while those two are still attached,
and the next `up` creates a network with a new identifier that they no longer
point at. The result is `Error response from daemon: network <id> not found`,
which names the network rather than the containers actually at fault.
`--remove-orphans` covers the case where the overlay has already been forgotten.

To keep the data instead, rename inside each store before bringing the rest up.
Note the order for Postgres: renaming a role **clears its password**, so it has
to be set again afterwards, and a database cannot be renamed while you are
connected to it — hence `-d postgres`.

```sh
docker compose up -d postgres
docker compose exec postgres psql -U rt_erp -d postgres \
  -c "ALTER ROLE rt_erp RENAME TO simple_erp;" \
  -c "ALTER ROLE simple_erp WITH PASSWORD 'simple_erp_dev';" \
  -c "ALTER DATABASE rt_erp RENAME TO simple_erp;"

docker compose up -d rabbitmq
docker compose exec rabbitmq rabbitmqctl add_user simple_erp simple_erp_dev
docker compose exec rabbitmq rabbitmqctl set_permissions -p / simple_erp ".*" ".*" ".*"
docker compose exec rabbitmq rabbitmqctl set_user_tags simple_erp administrator

# Photographs live in the bucket, and stored URLs name it. Copy, do not just
# create: minio-init makes an empty `simple-erp` bucket quite happily, and the
# map pins would then resolve to nothing.
docker compose up -d minio
docker compose exec minio sh -c "\
  mc alias set local http://localhost:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD && \
  mc mb --ignore-existing local/simple-erp && \
  mc mirror local/rt-erp local/simple-erp"
```

The seeder's identifiers are derived from a namespace that also carried the old
name, so a database seeded before the rename will gain a **second** set of
seeded rows rather than having the first updated in place. Run
`docker compose run --rm seed --reset` after migrating, or accept the duplicates
and clear them by hand.

### Production

```sh
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

Different in ways that matter:

- **Every secret is required.** Each is declared `${VAR:?}`, so a launch without
  them fails immediately rather than coming up with
  `change-me-in-any-real-deployment` as its signing key.
- **The stores publish no ports.** PostgreSQL, MinIO and RabbitMQ are reachable
  on the compose network and nowhere else; administration goes through
  `docker compose exec`.
- **The front-end is built and served by nginx**, which also proxies `/api` — so
  the browser sees one origin. `VITE_API_BASE_URL` is a **build argument**, not a
  runtime variable: Vite inlines it into the bundle, and setting it on a running
  container does nothing.
- **Two worker replicas**, no bind mounts, no reload, and CPU and memory limits.
- **The seeder is absent.** Production data is not fixture data.

Verify a configuration before deploying it — this renders the merged file and
fails on anything missing:

```sh
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml config --quiet
```

### Building the images on their own

```sh
docker build -t simple-erp-backend ./backend
docker build -t simple-erp-frontend --target production \
  --build-arg VITE_API_BASE_URL=/api ./frontend
```

The front-end Dockerfile has three targets: `development` (Vite), `build`, and
`production` (nginx). Tagged images are published to GHCR by
`.github/workflows/release.yml` on a `v*` tag.

→ [docs/09 — Running and deploying](docs/09-running-and-deploying.md) for what
each service does and the order they come up in.

## Repository layout

```
backend/          uv workspace — six members, strict dependency direction
  models/           domain models and configuration (pydantic)   ← depends on nothing
  storage/          ORM rows, mappers, repositories, migrations  ← models
  service/          business logic, solver, messaging, email     ← models, storage
  api/              FastAPI routers, middleware, dependencies    ← models, service
  worker/           broker consumer: solves plannings, notifies  ← models, storage, service
  seed/             idempotent development data                  ← models, storage, service
frontend/         React 19 + TypeScript + MUI, Vite
qa/               Robot Framework GUI campaign + coverage
docs/             the documentation set — start at docs/README.md
```

## Working on it

```sh
# Backend
cd backend
uv sync
uv run pytest                 # 938 test functions, hermetic
uv run ruff check . && uv run ruff format --check .
uv run ty check               # type checking — see docs/10-testing.md

# Front-end
cd frontend
npm ci
npm run dev
npm run lint && npm run typecheck && npm run test

# GUI campaign — needs the stack up
pip install -r qa/requirements.txt && rfbrowser init
robot --outputdir qa/results qa/robot/suites
```

## Documentation

The full set lives in [`docs/`](docs/README.md) — architecture, the domain
model, the quote workflow, the event pipeline, the planning computation,
configuration, deployment, testing and the house conventions.

Start with [`docs/README.md`](docs/README.md), which summarises each chapter and
says which one answers which question.

## Licence

See [`LICENCE`](LICENCE).
