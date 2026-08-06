# 09 — Running and deploying

## Compose

Three files. The base is never run alone.

| File | Contains |
|---|---|
| `docker-compose.yaml` | What the application **is**: postgres, minio, minio-init, rabbitmq, backend, worker, frontend |
| `docker-compose.dev.yaml` | Bind mounts, `--reload`, every port published, Mailpit, the seeder |
| `docker-compose.prod.yaml` | Restart policies, resource limits, no bind mounts, no published store ports, mandatory secrets |

```sh
# development
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build

# production
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

Everything that differs lives in an overlay, so the base file stays the one
description of the system rather than the development one with production bolted
on.

## What development adds

- **Source bind-mounted** over the image, so a save reloads. The virtualenv is
  deliberately *not* mounted: it belongs to the image, and shadowing it with the
  host's breaks on the first platform-specific wheel.
- **Every port published** — 5432, 5672, 15672, 9000, 9001, 8025 — so a
  developer can reach the database and the broker directly.
- **Mailpit** instead of a relay. `MP_SMTP_AUTH_ACCEPT_ANY` is load-bearing
  rather than convenience: `EmailService._deliver` calls `login()`
  unconditionally, so a catcher refusing authentication fails every send before
  a message is ever built.
- **The seeder**, once, after migrations.

## What production removes and adds

- No bind mounts, no reload, and **no published store ports** — the database is
  reachable on the compose network and nowhere else.
- `restart: unless-stopped` everywhere; CPU and memory limits.
- **Two worker replicas.** The queues are already separate, so scaling adds
  solver capacity with no code change.
- The front-end is built and served by **nginx**, which also proxies `/api` — so
  the browser sees one origin and CORS stops being load-bearing in production.
- **Every secret is `${VAR:?}`**, so a launch without them fails immediately
  rather than succeeding with a well-known key.

## Images

Two Dockerfiles.

`backend/Dockerfile` — two stages on `uv`. The manifests and lockfile are copied
first and synced, so a change to one module does not reinstall the world.
Runtime is `python:3.14-slim` with a non-root user, a `/ready` healthcheck, and
`conf/` copied in.

**Three services run this one image**: `backend`, `worker` and `seed`, each with
a different command. They share an explicit `image: simple-erp-backend:local` rather
than letting compose derive a name per service — without it, three services
building the same context produce three images that are only identical by
coincidence, which is the drift the arrangement exists to prevent. One name means
one build, and `docker compose build backend` rebuilds all three.

`frontend/Dockerfile` — three stages: `development` (Vite), `build` (with
`VITE_API_BASE_URL` as an `ARG`, because Vite inlines it), and `production`
(nginx). `frontend/nginx.conf` handles the SPA fallback, caches hashed assets
for a year, never caches `index.html`, and turns **buffering off for the SSE
path** — buffering would hold every frame until the connection closed.

## Order of operations

1. postgres, minio and rabbitmq come up and pass their healthchecks.
2. `minio-init` creates the `simple-erp` bucket and sets a public read policy — the
   map pins are `<img src>` loads straight from the bucket, so a private bucket
   leaves every pin broken. It runs to completion and exits.
3. **backend** runs `alembic upgrade head`, then serves. It owns the schema;
   two processes racing to migrate is how a deployment ends up half-upgraded.
4. **worker** waits for the backend, then consumes.
5. **seed** (development only) fills the database, idempotently.

## Seeding

`backend/seed/` — a console script, run once by compose.

Every identifier is a **UUID5 derived from a natural key**, so the seeder is an
upsert: running it twice writes nothing the second time. That is what lets it run
on every `up` without anybody having to remember whether they already did.

It writes through the **repositories**, not raw SQL — seeded data should
exercise the same validation the application does, or it is exactly the fixture
that turns out to be impossible to create through the UI.

Every address carries its coordinates. `PostalAddress` geocodes during
validation, so seeding forty addresses without them would fire forty live
requests at Nominatim's public instance and get the machine's IP blocked.

It produces: 1 company, 3 staff accounts, 12 assistants (and their accounts),
40 customers, 8 catalog entries, 54 quotes across every status, and next week's
service dates so a planning run has something to place.

## Health

`GET /health` answers without touching the database, so the container reports
healthy before PostgreSQL is up. `GET /ready` pings the database and answers 503
when it cannot — that is the one the Dockerfile healthcheck uses.

The connection manager connects **lazily on first use**, not in the lifespan, so
the API boots alongside its database rather than strictly after it. It retries
five times, two seconds apart.

## Credentials are baked in at first init

`POSTGRES_USER` / `POSTGRES_DB`, `RABBITMQ_DEFAULT_USER` and `MINIO_ROOT_USER`
are honoured **only when the store initialises an empty volume**. Every run
after that reads them from the volume, not from the environment — so changing
one in compose has no effect until the volume is destroyed.

This is worth knowing before it bites, because the symptom names the *new*
credential and so reads like a typo in the configuration:

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "simple_erp"
```

The application is asking for the right thing; the volume has never heard of it.
It surfaced when the product was renamed from `rt-erp` to SimpleERP, and it will
surface again for any rotation of these three values. Rotating a *password* is
different — the application-facing ones come from the environment on every
connection, and only the store's own initial superuser is fixed at init.

The README's **Upgrading a stack created before the SimpleERP rename** gives
both paths: destroy the volumes, or rename inside each store.

## Backups

Two volumes hold everything durable: `postgres-data` and `minio-data`.
`rabbitmq-data` holds undelivered messages — worth keeping across a restart, not
worth backing up.

There is no backup job in this repository. That is a gap, not a decision.
