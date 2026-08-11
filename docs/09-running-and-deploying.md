# 09 — Running and deploying

Everything that runs the application lives under **`infra/`**. The application
itself is in `backend/` and `frontend/`; `infra/` holds the descriptions of how
to stand it up — compose, the Helm chart, the Argo CD applications, the cluster
add-ons and the observability configuration.

## Compose

Four files, under `infra/compose/`. The base is never run alone.

| File | Contains |
|---|---|
| `docker-compose.yaml` | What the application **is**: postgres, minio, minio-init, rabbitmq, migrate, backend, worker-planning, worker-notifications, frontend — plus pgbouncer behind a profile |
| `docker-compose.dev.yaml` | Bind mounts, `--reload`, every port published, Mailpit, the seeder, and the observability chain — Prometheus, Grafana, Loki, Tempo, Alloy and the OpenTelemetry Collector |
| `docker-compose.prod.yaml` | Restart policies, per-role resources and replicas, no bind mounts, no published store ports, mandatory secrets |

```sh
cd infra/compose
cp .env.example .env

# development — COMPOSE_FILE in .env selects the overlay
docker compose up --build

# or explicitly, from the repository root
docker compose -f infra/compose/docker-compose.yaml \
               -f infra/compose/docker-compose.dev.yaml up --build

# production
docker compose -f infra/compose/docker-compose.yaml \
               -f infra/compose/docker-compose.prod.yaml up -d
```

Everything that differs lives in an overlay, so the base file stays the one
description of the system rather than the development one with production bolted
on.

### Two things the move broke, and how they are held

**The project name is pinned.** Compose names a project after the directory
holding the first compose file, so moving these under `infra/compose` would have
renamed it from `rt-erp` to `compose` — and every volume with it. Because the
stores bake their credentials in when they first initialise an *empty* volume,
the symptom is not an empty database but the authentication failure below,
naming the right user, reading exactly like a typo in the configuration:

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "simple_erp"
```

`name: rt-erp` at the top of the base file is what prevents it.
`docker volume ls | grep rt-erp_` is the check.

**`.env` belongs beside the compose files.** Compose reads it from the project
directory — the directory of the first `-f` file — so one left at the repository
root is silently not read, and the stack comes up on the development defaults
without saying so.

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

**Five services run this one image**: `migrate`, `backend`, `worker-planning`,
`worker-notifications` and `seed`, each with a different command. They share an
explicit `image: simple-erp-backend:local` rather than letting compose derive a
name per service — without it, five services building the same context produce
five images that are only identical by coincidence, which is the drift the
arrangement exists to prevent. One name means one build, and
`docker compose build backend` rebuilds all five.

`frontend/Dockerfile` — three stages: `development` (Vite), `build` and
`production` (nginx). **No build argument**: the API's address used to be
inlined into the bundle, which meant one image per environment and a promotion
that rebuilt rather than promoted — the digest tested in staging was never the
digest that reached production. The image ships a `/config.json` naming the
same-origin `/api`, read once before the first render, and a deployment needing
a different one mounts over it (a ConfigMap in the cluster). nginx serves that
file `no-store`, because a cached copy would leave a promoted image pointing at
the environment it was promoted *from*. `frontend/nginx.conf` handles the SPA fallback, caches hashed assets
for a year, never caches `index.html`, and turns **buffering off for the SSE
path** — buffering would hold every frame until the connection closed.

## Order of operations

1. postgres, minio and rabbitmq come up and pass their healthchecks.
2. `minio-init` creates the `simple-erp` bucket and sets a public read policy — the
   map pins are `<img src>` loads straight from the bucket, so a private bucket
   leaves every pin broken. It runs to completion and exits.
3. **migrate** runs Alembic to `head` and exits. Everything that reads the
   schema waits on `service_completed_successfully`.
4. **backend** serves. It no longer migrates: that was the first half of its
   start command, which is fine with one replica and a race with two — "how a
   deployment ends up half-upgraded" by this chapter's own account. Exactly one
   process migrates now, and the chart expresses the same thing as a
   `pre-install,pre-upgrade` hook Job.
5. **worker-planning** and **worker-notifications** consume, independently of
   each other and of the API.
6. **seed** (development only) fills the database, idempotently.

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

## What the seed prices at

Every service in the seeded catalogue bills at the **same** hourly rate,
`Dataset.HOURLY_RATE_HT` — one constant rather than a figure per entry, so
"every service costs the same" is a property of the seed rather than eight
literals that happen to agree.

It is deliberately the same figure as `PricingConfig.base_hourly_rate_ht`, which
makes a demo total checkable by hand: hours x the rate, times any weekday or
holiday surcharge. The only thing that then varies between two lines is the VAT
their categories carry — which is the thing worth showing, since the category is
chosen per quote line rather than per service.

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

## Kubernetes

A Helm chart in `infra/chart`, reconciled by Argo CD. The chart deploys the
application and nothing else: PostgreSQL, RabbitMQ, the ingress controller and
the metrics stack are installed by `infra/bootstrap`, because they outlive any
one release and a chart that owned them would uninstall cert-manager on a failed
rollback.

```sh
helm lint infra/chart --set global.image.tag=$(git rev-parse --short HEAD)
helm template simple-erp infra/chart \
  -f infra/chart/values.yaml -f infra/chart/values-dev.yaml \
  --set global.image.tag=$(git rev-parse --short HEAD)
```

`global.image.tag` is **required and has no default** — the chart fails to
render without one rather than falling back to `latest`, because a moving tag
makes a rollback mean "whatever that tag points at now".

### What the chart refuses to render

`templates/common/guards.yaml` holds checks for five mistakes that are silent at
runtime: the pods start, report Ready, and do the wrong thing.

| Refused | Because |
|---|---|
| `solverWorkers` ≠ the planning worker's CPU limit | The budget is wall-clock; more threads than cores means the kernel throttles the cgroup and thirty seconds takes a minute. The run still reports as having used its budget |
| CPU request ≠ CPU limit on the planning worker | Anything but Guaranteed QoS is the same throttling from the other side |
| A grace period under 60s on the planning worker | Kubernetes' default is 30, which is *exactly* the solve budget — a scale-down would `SIGKILL` mid-solve |
| `workerNotifications` scaling to zero | A badge should be instant; a cold start is not |
| An empty `integrations.providers` | The cluster would serve every screen except the one that makes the agency compliant: an e-invoicing gallery with nothing to connect |

### Two flags a cluster must set deliberately

`billingWebhook.enabled` and `integrations.providers` are what make an invoice
leave the building. The first is off by default in every values file, because
emailing customers is a decision; with it off a bill marked paid publishes its
event, the notifications worker declines to call, and nothing reaches the
certified platform. The second is the catalogue of platforms the gallery offers,
and the guard above refuses an empty one.

Both were absent from the chart entirely until the e-invoicing work: a cluster
ran the model's defaults — a disabled webhook pointed at `localhost` — which is
silent, and is the reason it went unnoticed.

### The two workers scale on different things

The API is scaled by a CPU HPA. That is right for it and wrong for the workers:
a consumer waiting on a broker burns almost no CPU, so the same autoscaler would
never scale one however deep its queue. Both workers are scaled by **KEDA on
queue depth** instead.

| | planning | notifications |
|---|---|---|
| `operation` | `sum` — maximise throughput | `max` — one agency's backlog must not decide everybody's replica count |
| `minReplicaCount` | 1 | 1, and the chart refuses 0 |
| QoS | Guaranteed | Burstable |
| Grace period | 90s | 30s |
| Node pool | its own, tainted, in production | wherever |

**One `ScaledObject` covers every agency.** The queues are per-agency, so
without the RabbitMQ scaler's regex support this would be one object per agency
— created and destroyed as agencies come and go, by something that would have to
watch the database to know. The pattern excludes the dead-letter queues:
messages there have been given up on, and scaling up to consume them would spin
workers against work nothing will accept.

### Argo CD

One `Application` per environment in `infra/argocd`. Dev auto-syncs with prune
and self-heal; staging prunes but does not self-heal, because a manual change
there is usually somebody mid-incident and reverting it under them is the wrong
help. **Production has no automated sync at all**: the migration hook is
irreversible, and a sync that ran on its own could migrate a schema nobody was
watching.

Image tags are absent from the values files. CI passes
`--set global.image.tag=<git sha>` at sync time, so a rollback is a sync to a
previous revision rather than a commit that has to be reverted.

### One thing with a deadline

The queues are declared `x-queue-type: quorum`, and **redeclaring an existing
classic queue with a different type is a `PRECONDITION_FAILED`, not an
upgrade**. A deployment that ran on classic queues needs them drained and
deleted before this version will consume at all. Do it while there is at most
one deployment to drain. → [05](05-events-and-notifications.md)

## Backups

Two volumes hold everything durable: `postgres-data` and `minio-data`.
`rabbitmq-data` holds undelivered messages — worth keeping across a restart, not
worth backing up.

**A third thing is durable and is not a volume: `EINVOICING_CREDENTIAL_KEY`.**
Every other secret is a credential for something that can be issued again — a
new database password, a new signing key, a rotated S3 pair. This one is the
only thing that can read an agency's stored e-invoicing platform credentials
back, so losing it means every agency must re-enter its certified platform's API
key before it can transmit an invoice again. Whatever store holds it needs the
same backup discipline as the database, and restoring `postgres-data` without it
restores rows nothing can decrypt.

It is read by the API alone. A worker publishes `bill.paid` and calls the
loopback webhook; the transmission — and so the one decryption — happens in the
API process, which is why the compose files set it there and nowhere else.

There is no backup job in this repository. That is a gap, not a decision.
