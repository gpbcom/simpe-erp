# 01 — Architecture

## Processes

Seven things run. Five of them are the application.

| Process | Image | What it does |
|---|---|---|
| **migrate** | `backend/Dockerfile`, `command: ["migrate"]` | Runs Alembic to `head`, once, and exits. Everything else waits for it |
| **api** | the same image | Serves HTTP and holds the SSE connections |
| **worker-planning** | the same image, `["worker", "planning"]` | Consumes `planning-runs`: the CP-SAT solves |
| **worker-notifications** | the same image, `["worker", "notifications"]` | Consumes `quote-notifications`: notifications and email |
| **frontend** | `frontend/Dockerfile` | Vite dev server, or nginx serving a built bundle |
| postgres | `postgres:17-alpine` | Everything durable |
| minio | `minio/minio` | Portraits — of assistants, and of the accounts that sign in |
| rabbitmq | `rabbitmq:4-management` | Events between the API and the workers |

**Four processes, one image, four entry points.** Building one image and running
it four ways is what stops them drifting apart — which is exactly what happens
once a worker gets a Dockerfile of its own.

**Exactly one process migrates, and it is not the API.** `alembic upgrade head`
used to be the first half of the API container's start command, which is fine
with one replica and a race with two — "how a deployment ends up half-upgraded"
by this chapter's own account. It is now its own entry point: a one-shot
`migrate` service in compose, and a `pre-install,pre-upgrade` hook Job in the
chart. The same arrangement described twice, rather than two that have to agree.

### Why the worker is two deployments

They are unlike each other in the way that matters to a scheduler. A solve is
CPU-bound and pins its cores for a thirty-second budget; a notification fan-out
is I/O-bound and finishes in milliseconds. In one process they scale together —
so a manager waits half a minute to be told a quote needs looking at, because
the pod is mid-solve.

Split, each scales on its own queue's depth, gets its own resources, and can be
put on its own node pool. It also leaves room for a third role without
disturbing either.

**Neither role owns the control plane.** `company.created` is consumed by
*both*, each on an exclusive queue of its own, because each has queues to
declare when an agency is founded. Making it a third deployment would hand each
announcement to one process and leave the other serving every agency but the new
one.

## Layers

The backend is a `uv` workspace of six members with a strict, one-directional
dependency graph:

```
models  ←  storage  ←  service  ←  api
                          ↑
                          └──  worker
                          └──  seed
```

| Member | Holds | May import |
|---|---|---|
| `models` | Pydantic domain models, configuration, enums, exceptions | nothing first-party |
| `storage` | ORM rows, mappers, repositories, migrations, S3 | `models` |
| `service` | Business logic, the solver, messaging, email | `models`, `storage` |
| `api` | Routers, middleware, dependency wiring | `models`, `service` |
| `worker` | Broker consumer and its handlers | `models`, `storage`, `service` |
| `seed` | Development data | `models`, `storage`, `service` |

**The worker does not depend on `api`**, deliberately. A background consumer
that pulled in FastAPI and uvicorn to read one YAML file would make the graph a
ring; it duplicates fifteen lines of logging setup instead, and the duplication
is documented where it sits.

## Package layout

Both `models` and `storage` are grouped by **domain first**, and the two trees
line up on purpose.

Inside `models`, each domain package holds one package **per aggregate** — the
entity, the value objects that only exist as part of it, and its exceptions:

```
models/people/
  hca/                     customer/            hca_application/
    hca.py                   customer.py          hca_application.py
    availability_slot.py     exceptions/          exceptions/
    certification.py
    skill.py
    driving_license.py
    exceptions/
```

An assistant's certifications, skills, licence and absences live *with* the
assistant because none of them means anything on its own — a certification with
no holder is not a record anybody keeps, and neither is a skill. `models/planning` is grouped the same way, around
`intervention/`, `planning_run/` and `hca_planning/`, and `schemas/requests` and
`schemas/responses` around the entity each payload acts on.

Each aggregate package re-exports its models, so `from models.people.hca import
Hca, Certification, Skill` works and the file a class happens to sit in stays an
internal detail. Exceptions are imported from the explicit
`models.people.hca.exceptions` — a model importing its own package would be a
cycle.

`storage` mirrors those domain names rather than inventing its own:

```
storage/orm/people/hca_row.py
storage/mappers/people/hca_mapper.py
storage/repositories/people/hca.py
```

A row, its mapper and its repository sit at the same path under three roots.
Changing an entity means touching all three, and a layout where they are found
the same way each time is what stops the third being forgotten. What stays at
each root is only what belongs to no entity: `orm/base.py`, `mappers/`'s
`base_mapper`, `person_mapper` and `timestamp_normalizer`, and
`repositories/base.py`.

`orm/__init__.py` re-exports every row. That is not convenience — Alembic and
the test schema builder need one import that reaches every table, and a row no
module imports is a table `create_all` silently omits.

Alongside those domain packages, `base/` holds what several of them share
rather than what any one of them is: `Person` — the identity fields and
validators every human record carries — and the `PortraitHolder` mixin for
the two that hold a photograph. Nothing is stored as a `Person`; it is a
base, and the rule for extending it is in [12](12-conventions.md).

### What each layer refuses to do

- **`models` never touches a database or a network** — with one exception worth
  knowing: `PostalAddress` geocodes during validation. That is why the seeder
  supplies coordinates, and why the test suite has an autouse fixture that
  neutralises it.
- **`storage` never commits.** A repository is handed a session already inside a
  transaction, so a service performing several writes gets one transaction
  rather than one per call.
- **`service` never raises `HTTPException`.** It raises its own `MT*` exception,
  which travels untouched to `api/exception_handlers.py` and is translated
  there, once.
- **`api` contains no business logic.** An endpoint validates its payload,
  calls one service method, and returns. Anything longer belongs a layer down.

## Request flow

```
        ┌──────────────── CORSMiddleware ────────────────┐
        │   ┌──────────── AuthMiddleware ────────────┐   │
        │   │   ┌──────── TransactionMiddleware ──┐  │   │
   ───▶ │   │   │   router → guard → service →    │  │   │ ───▶
        │   │   │           repository → mapper   │  │   │
        │   │   └─────────────────────────────────┘  │   │
        │   └────────────────────────────────────────┘   │
        └────────────────────────────────────────────────┘
```

The order is load-bearing in both directions:

- **CORS outermost**, so a rejected credential still carries the CORS headers.
  Without that a browser reports an opaque network error instead of the 401 it
  was given.
- **Transaction innermost**, so it sees the response the router produced with
  the request's session still open. It commits **before** the response body is
  written, which is why creating an assistant and immediately registering their
  account works rather than failing about one time in five.

`AuthMiddleware` resolves the bearer token and attaches the account to
`request.state.user`. Authentication is middleware rather than a dependency so
that a route added without a guard is still *authenticated* — forgetting a
dependency then leaves the endpoint unauthorised rather than open.
**Authorisation** stays in the per-route guards, which is where it belongs.

## The read and write paths

A **read** goes router → service → repository → mapper → domain model. The
mapper re-runs the model's validators on the way out, so a row written by an
older schema is caught here rather than propagating a malformed object.

A **write** goes domain model → mapper → row → session. Insert and update share
one `_apply_fields` per mapper, which is what stops a column being written on
create and silently forgotten on update.

`BaseMapper` carries all of that once. A concrete mapper supplies only the two
directions that genuinely differ per table.

## Where the asynchronous work lives

The API answers **202** to a planning request and publishes
`planning.run.requested`; the worker consumes it, solves, and stores the plan.
The message is acknowledged only once the handler returns, so a worker killed
mid-solve leaves the message for the next one.

That replaced FastAPI `BackgroundTasks`, which lost the run entirely on a
restart and occupied a web worker for the thirty seconds a solve takes.

→ [05 — Events and notifications](05-events-and-notifications.md)
