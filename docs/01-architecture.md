# 01 — Architecture

## Processes

Five things run. Three of them are the application.

| Process | Image | What it does |
|---|---|---|
| **api** | `backend/Dockerfile` | Serves HTTP, holds the SSE connections, runs the migrations on boot |
| **worker** | the same image, `command: ["worker"]` | Consumes the broker: solves plannings, writes notifications, sends email |
| **frontend** | `frontend/Dockerfile` | Vite dev server, or nginx serving a built bundle |
| postgres | `postgres:17-alpine` | Everything durable |
| minio | `minio/minio` | Assistant photographs |
| rabbitmq | `rabbitmq:4-management` | Events between the API and the worker |

The worker runs the **same image** as the API with a different entry point.
Building one image and running it two ways is what stops the two drifting apart
— which is exactly what happens once a worker gets a Dockerfile of its own.

**The API owns the schema.** It runs `alembic upgrade head` before serving, and
the worker waits on it. Two processes racing to migrate the same database is how
a deployment ends up half-upgraded.

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
