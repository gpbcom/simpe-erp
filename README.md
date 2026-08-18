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
  <a href="#kubernetes">Kubernetes</a> ·
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

Four application processes and three stores. The API, both workers and the
migrator run the **same image** with different entry points — one image built
four ways cannot drift the way four Dockerfiles do.

```
                     ┌──────────────┐
   browser ────────▶ │  React SPA   │ ─────────┐
                     └──────────────┘          │  REST + SSE
                                               ▼
   ┌────────────────┐        ┌──────────────┐  ┌────────┐
   │ worker         │ ◀────▶ │  RabbitMQ    │◀─│  API   │
   │  · planning    │ events └──────────────┘  └────────┘
   │  · notifications│                             │
   └────────────────┘                              │
        │                                          │
        └──────────▶ PostgreSQL ◀──────────────────┘
                     MinIO (photographs)
```

| Process | Does |
|---|---|
| **migrate** | Runs Alembic to `head`, once, and exits. Everything else waits for it |
| **api** | Serves HTTP and holds the SSE connections |
| **worker-planning** | Consumes `planning-runs`: runs the CP-SAT solves |
| **worker-notifications** | Consumes `quote-notifications`: writes notifications, sends email |
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
| Memory | ~5 GB free — the solver and the broker are the hungry parts, and the observability chain adds about a gigabyte |
| Ports | 5173, 8000, 5432, 5672, 15672, 9000, 9001, 1025, 8025, 9101, 9102, and 3000, 3101, 9090, 4317, 4318 for observability |

The development overlay publishes every one of those ports so you can reach the
database and the broker directly. If something already holds one, either stop it
or drop that mapping from `infra/compose/docker-compose.dev.yaml`.

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
cp infra/compose/.env.example infra/compose/.env
make up-build
```

`make` is the short way in: the compose files live under `infra/compose/`, so
every raw command needs two `-f` flags, and the `Makefile` at the root passes
both for you. Spelled out, that first command is:

```sh
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml up --build
```

That brings up PostgreSQL, MinIO, RabbitMQ, the API, both workers, Mailpit, the
Vite dev server and the whole observability chain, runs the migrations once
through the `migrate` service, and seeds a working agency — 12 assistants,
40 customers, a service catalog and 54 quotes spread across every status.

Wait for `Bucket simple-erp is ready.` and the seeder's credential block. The first
build takes a few minutes, and afterwards a start is seconds.

| | |
|---|---|
| Application | <http://localhost:5173> |
| API and its docs | <http://localhost:8000> · <http://localhost:8000/docs> · <http://localhost:8000/redoc> |
| Caught email | <http://localhost:8025> |
| Broker management | <http://localhost:15672> — `simple_erp` / `simple_erp_dev` |
| Object store console | <http://localhost:9001> — `simple_erp_dev` / `simple_erp_dev_secret` |

### Observability

Every process serves the same three probes, on the same three paths. `/health`
answers whether it is alive, `/ready` whether it can reach what it needs, and
`/metrics` a Prometheus exposition. **A worker that is up but cannot reach the
broker answers 200 on the first and 503 on the second**, which is the whole
reason there are two.

| Process | Liveness | Readiness | Metrics |
|---|---|---|---|
| API | <http://localhost:8000/health> | <http://localhost:8000/ready> | <http://localhost:8000/metrics> |
| Planning worker | <http://localhost:9101/health> | <http://localhost:9101/ready> | <http://localhost:9101/metrics> |
| Notification worker | <http://localhost:9102/health> | <http://localhost:9102/ready> | <http://localhost:9102/metrics> |

The dashboards behind them come up with everything else — **the development
stack always runs the full observability chain**, so a panel that has rotted is
something you find on a Tuesday rather than the day you needed it. It costs five
more containers and roughly a gigabyte of memory, which is the deliberate trade.

| | |
|---|---|
| Grafana | <http://localhost:3000> — no sign-in, anonymous admin · <http://localhost:3000/explore> to query the logs |
| Prometheus | <http://localhost:9090> · [targets](http://localhost:9090/targets) · [rules](http://localhost:9090/rules) · [alerts](http://localhost:9090/alerts) |
| Loki | <http://localhost:3101/ready> · <http://localhost:3101/metrics> — an API, not a UI; read the logs in Grafana. Published on 3101 because the RobotCode editor extension holds 3100 |
| OTLP ingest | `localhost:4317` (gRPC) · `localhost:4318` (HTTP) — endpoints the collector accepts spans on, not pages |

**Loki is published for `curl`, not for a browser** — it serves an API and no
interface of its own, and logs are read in Grafana. What the port buys is the
one question Grafana cannot answer. An empty Explore pane looks identical
whether Alloy is shipping nothing, Loki is refusing it, or the query is simply
wrong; `/ready` and `/metrics` separate those in one request each.

**Tempo and Alloy still publish nothing, on purpose.** Grafana reaches Tempo
over the compose network, and Alloy scrapes the container runtime's own logs
rather than serving anything — so a port for either would be another way to
look at data Grafana already shows, and another thing to remember is running.

The Prometheus targets page is the one to open first when a panel is empty — an
exporter that is down there explains a blank dashboard faster than the dashboard
does. → [docs/14](docs/14-observability.md)

Sign in with any of the seeded accounts, all sharing the password
`simple-erp-demo-2026`:

| Role | Address | Lands on |
|---|---|---|
| Administrator | `admin@simple-erp.fr` | The quote screen |
| Manager, runs the seeded team | `manager@simple-erp.fr` | The quote screen |
| Manager, runs no team | `manager2@simple-erp.fr` | The quote screen |
| Manager, on the rounds | `marc.dubois@simple-erp.fr` | The quote screen |
| Assistant | `luc.martin@simple-erp.fr` | Their own planning |

Every seeded assistant signs in as `firstname.lastname@simple-erp.fr`.

The seeded company operates from two sites — **Siège Paris**, its head office,
and **Antenne Lyon**, a branch that holds nobody — and every seeded person and
quote belongs to one team, *Equipe principale*, run by `manager@simple-erp.fr`.
Sign in as `manager2@simple-erp.fr` to see the other side of that: they run no
team, so their quote book, workforce and household list are all empty while the
administrator's are full. That is the team narrowing, not a broken screen.

Marc Dubois is a manager who still covers rounds — they hold both a manager's
role and an assistant record. Sign in as them to see the employment section of
**My account** in its editable form, where the contract type, the
qualifications and *whether this person goes out on rounds* can be changed.
The same section renders locked for Luc Martin, who holds the assistant role.

## Docker

Three compose files. **The base is never run alone** — it describes what the
application *is*, and an overlay says how you want to run it.

| File | Adds |
|---|---|
| `infra/compose/docker-compose.yaml` | The services themselves: postgres, minio, minio-init, rabbitmq, **migrate**, backend, **worker-planning**, **worker-notifications**, frontend — plus `pgbouncer` behind a `pooled` profile, which an ordinary `up` does not start |
| `infra/compose/docker-compose.dev.yaml` | Source bind-mounts, live reload, every port published, Mailpit, the seeder, and the whole observability chain — Prometheus, Loki, Tempo, Grafana, Alloy and the OpenTelemetry Collector |
| `infra/compose/docker-compose.prod.yaml` | Restart policies, per-role resource limits and replicas, nginx, **mandatory secrets** |

`pgbouncer` is off by default because it is there to be exercised rather than
needed: `asyncpg` caches server-side prepared statements per connection, and
under transaction pooling a "connection" is a different backend from one
transaction to the next. The engine passes `statement_cache_size=0`
unconditionally to prevent that, and `--profile pooled` is what proves the
setting still works. → [docs/13](docs/13-kubernetes.md)

Observability is part of the dev overlay rather than an overlay of its own —
see [Observability](#observability) above for the addresses. It reads the
**same** alert rules the Helm chart ships (`infra/chart/rules/`), so an alert
cannot fire on a laptop and not in the cluster.
→ [docs/14](docs/14-observability.md)

Because two `-f` flags on every command gets tedious, there are two ways round
it. Either use the `Makefile` at the root, which passes both on every target:

```sh
make            # list the targets
make up         # start, in the background
make stop       # stop, keeping the containers and the data
make down       # stop and remove the containers, keeping the data
```

…or export the pair once per shell and use `docker compose` directly:

```sh
export COMPOSE_FILE=infra/compose/docker-compose.yaml:infra/compose/docker-compose.dev.yaml
```

**Whichever you pick, use the same two files to go down as you did to come up.**
`mailpit`, `seed` and the whole observability chain are declared *only* in the
dev overlay, so a bare `docker compose down` leaves them running attached to a
network it has just deleted — and the next `up` fails with
`network <id> not found`, naming the network rather than the containers that are
really the problem. The `Makefile` exists mostly to make that unreachable.

Every raw command below assumes `COMPOSE_FILE` is exported. Without it, spell
both files out.

### Day to day

| `make` | `docker compose` | |
|---|---|---|
| `make up` | `docker compose up -d` | start, in the background |
| `make up-build` | `docker compose up -d --build` | rebuild first — after a dependency change |
| `make ps` | `docker compose ps` | what is running, and is it healthy |
| `make logs S=backend` | `docker compose logs -f backend` | follow one service |
| — | `docker compose logs -f backend worker-planning` | …or several |
| `make stop` | `docker compose stop` | stop, keeping the data |
| `make down` | `docker compose down --remove-orphans` | stop and remove the containers |
| `make seed` | `docker compose run --rm seed` | re-run the seeder |
| `make clean` | `docker compose down -v && … up --build` | **destroys the data** — see [Starting over](#starting-over) |
| `make urls` | — | print every address the stack publishes |
| `make replan-config` | `docker compose restart worker-planning` | pick up an edited `backend/conf/app.dev.yaml` |

`make replan-config` is worth knowing about because `backend/conf/` is
bind-mounted: the solver settings can be changed and tried without a rebuild,
and the planning worker only reads them at start.

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
docker compose exec backend alembic -c conf/alembic.ini current
docker compose exec backend alembic -c conf/alembic.ini upgrade head
docker compose exec backend bash                   # a shell in the API container
docker compose exec postgres psql -U simple_erp simple_erp # a database prompt

docker compose run --rm seed                       # re-run the seeder (idempotent)
```

The seeder writes nothing on a second run — every identifier is derived from a
natural key, so it upserts. Running it again is always safe.

**The test suite is not among these**, and cannot be: the runtime image carries
no `uv` and no test framework, and `backend/.dockerignore` keeps `tests/` out of
the build context entirely. That is deliberate — the image that runs the suite
would be the image that reaches production. The suite is hermetic, so it needs
none of this stack anyway: run it on the host, which is also what CI does.

```sh
cd backend && uv run pytest
```

### Starting over

```sh
make clean                                     # both steps below, with both -f flags
```

or, spelled out:

```sh
DEV="-f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml"
docker compose $DEV down -v --remove-orphans   # containers AND volumes: a clean database
docker compose $DEV up --build                 # rebuild and reseed from nothing
```

`-v` destroys `postgres-data`, `minio-data` and `rabbitmq-data`. In development
that is the fastest way back to a known state. Anywhere else it is data loss.
`make clean` is the same thing and just as destructive — it is not a cache
sweep.

**Use the same `-f` files to go down as you did to come up**, which is the one
thing the `Makefile` guarantees. `mailpit` and `seed` are defined only in the
dev overlay, so a bare `docker compose down` leaves them behind attached to the
network it has just deleted — and the next `up` fails with
`network <id> not found`, naming the network rather than the two containers that
are really the problem.

### Rebuilding one image

```sh
docker compose build backend          # the API, both workers and the migrator share this image
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
| No notifications arrive | `worker-notifications` is down, or RabbitMQ never went healthy — it takes ~20 s on a cold start |
| Login rejects the seeded accounts | The seeder did not run: `docker compose run --rm seed` |
| A port is already in use | Something else holds 5432, 8000 or 5173; stop it, or drop that port from the dev overlay |
| `network <id> not found` on `up` | A previous `down` used a different `-f` set — see **Starting over** |
| `password authentication failed for user "simple_erp"` | A volume from before the rename — see below |

### After the compose files moved into `infra/compose`

The base file declares `name: rt-erp`, so the project name — and every volume
name with it — is unchanged by the move. If you have removed that line, or you
run compose from somewhere that does not pick the base file up, the project is
named after the directory instead and the stack comes up against three empty
volumes.

That does **not** look like an empty database. The stores bake their credentials
in when they first initialise an empty volume, so what you get is the
authentication failure below — naming the right user, which reads exactly like a
typo in the configuration.

```sh
docker volume ls | grep rt-erp_   # postgres-data, minio-data, rabbitmq-data
```

If those exist and the stack is not using them, the data is fine and the project
name is wrong. Put `name: rt-erp` back.

Note also that `.env` now belongs **beside the compose files**, in
`infra/compose/`. Compose reads it from the project directory, which is the
directory of the first `-f` file; one left at the repository root is silently
not read, and the stack comes up on the development defaults without saying so.

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
backend reaches it first. The broker and the object store would fail next.

For a development stack, throw the volumes away — the data is seeded, and
reseeding takes seconds:

```sh
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml down -v --remove-orphans
docker network rm rt-erp_rt-erp                       # the network named after the old product
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml up --build
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
seeded rows rather than having the first updated in place. **The seeder takes no
arguments** — its entry point accepts `argv` only so the console script matches
the others, and ignores it — so there is no `--reset` to run. Either drop the
volumes and reseed from nothing, which is the development answer, or clear the
duplicate rows by hand.

### Production

```sh
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.prod.yaml up -d
```

Different in ways that matter:

- **Every secret is required.** Each is declared `${VAR:?}`, so a launch without
  them fails immediately rather than coming up with
  `change-me-in-any-real-deployment` as its signing key.
- **The stores publish no ports.** PostgreSQL, MinIO and RabbitMQ are reachable
  on the compose network and nowhere else. Administration goes through
  `docker compose exec`.
- **The front-end is built and served by nginx**, which also proxies `/api` — so
  the browser sees one origin. The API's address is **not** built into the
  bundle: it is read at start-up from `/config.json`, which ships in the image
  naming that same-origin `/api`. That is what makes one image promotable
  dev → staging → production rather than one image per environment.
- **Two planning workers and one notification worker**, sized separately: a
  solve wants whole cores, a fan-out wants none. No bind mounts, no reload.
- **The seeder is absent.** Production data is not fixture data.

Verify a configuration before deploying it — this renders the merged file and
fails on anything missing:

```sh
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.prod.yaml config --quiet
```

### Building the images on their own

```sh
docker build -t simple-erp-backend ./backend
docker build -t simple-erp-frontend --target production ./frontend
```

The front-end Dockerfile has three targets: `development` (Vite), `build`, and
`production` (nginx). Tagged images are published to GHCR by
`.github/workflows/release.yml` on a `v*` tag.

→ [docs/09 — Running and deploying](docs/09-running-and-deploying.md) for what
each service does and the order they come up in.

## Kubernetes

Compose is one description of the system; `infra/chart` is the other, and they
are kept deliberately alike. The same five workloads, the same image built five
ways, the same one-shot migrator ahead of everything else — expressed as a Helm
`pre-install,pre-upgrade` hook Job rather than a `service_completed_successfully`
dependency.

```sh
helm lint infra/chart --set global.image.tag=$(git rev-parse --short HEAD)
helm template simple-erp infra/chart -f infra/chart/values-dev.yaml \
  --set global.image.tag=$(git rev-parse --short HEAD)
```

What the chart does **not** contain is the part worth knowing: PostgreSQL,
RabbitMQ, MinIO and PgBouncer are not in it. In compose they are services
because a laptop has to run something. In a cluster they are operator-managed
and installed by [`infra/bootstrap`](infra/bootstrap/README.md). They outlive
any one release, and a chart that owned them would uninstall cert-manager on a
failed rollback and take every certificate with it. Mailpit and the seeder have
no cluster equivalent at all — one catches development email, the other writes
fixture data.

Argo CD reconciles it, one `Application` per environment in `infra/argocd`.
Production syncs **manually**: the migration hook is irreversible, and a sync
that ran on its own could migrate a schema nobody was watching.

→ [docs/13 — Kubernetes](docs/13-kubernetes.md) ·
[docs/14 — Observability](docs/14-observability.md)

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
infra/            everything that runs it
  compose/          the four compose files, and .env
  chart/            the Helm chart: five workloads, KEDA, alert rules
  argocd/           one Application per environment
  bootstrap/        the cluster add-ons the chart deliberately does not own
  observability/    collector, Prometheus, Loki, Tempo, Grafana — shared with compose
qa/               Robot Framework GUI campaign + coverage
docs/             the documentation set — start at docs/README.md
Makefile          dev-stack shortcuts; passes both compose -f flags for you
```

The `Makefile` is the one infrastructure file **not** under `infra/`, on
purpose: it is the entry point, and an entry point nobody can find is not one.
It drives the dev overlay only — production keeps its explicit `-f` flags, where
being explicit is worth the length.

## Working on it

```sh
# Backend
cd backend
uv sync
uv run pytest                 # 1,866 test functions, hermetic
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
