# 08 — Configuration

YAML for settings, environment variables for secrets, and nothing in between.

## The files

| File | Used by | Differs by |
|---|---|---|
| `backend/conf/app.yaml` | a process run on the host | `localhost` addresses; broker and email **off** |
| `backend/conf/app.dev.yaml` | the development compose overlay | container addresses; email **on**, pointed at Mailpit |
| `backend/conf/app.docker.yaml` | the base and production stacks | container addresses; broker **on**, email off |
| rendered by the chart | the cluster | a ConfigMap, mounted at `conf/app.k8s.yaml` |

Two logging configurations sit beside them, selected by **`SIMPLE_ERP_LOGGER`**
rather than by a key in `app.yaml` — logging has to be configured before that
file is read, because a failure loading it is the first thing worth logging.

| File | Writes |
|---|---|
| `backend/conf/logger.yaml` | Colourised console **and** a rotating `logs/backend.log` |
| `backend/conf/logger.k8s.yaml` | JSON to stdout, and nothing to disk |

The second is what a container uses. A rotating file inside one is invisible
from outside it, unbounded on a layer nobody sized for it, and gone when the pod
is replaced — and JSON is what makes anything a caller attached with `extra=`
(`company_id`, `routing_key`, `run_id`) a queryable field rather than something
to grep a sentence for.

Selected with `SIMPLE_ERP_CONFIG`. `AppConfig.load()` resolves it relative to the
working directory, then relative to `backend/`, then falls back to
`conf/app.yaml`.

Alembic loads the same file, deliberately — so migrations and the application
can never disagree about which database they mean.

## The sections

| Section | Holds |
|---|---|
| `server` | Host, port, title, version, **`cors_origins`** |
| `database` | Host, port, name, user, `password_env`, pool sizing |
| `auth` | `jwt_secret_env`, algorithm, `access_token_expire_minutes`, `allow_company_registration` |
| `pricing` | Base hourly rate, weekday surcharges, holiday surcharges |
| `planning` | Working-day bounds, lunch window, travel speeds, solver budget, penalties, **seed values** for the manager-owned settings |
| `geocoding` | Nominatim base URL, user agent, timeout, country codes |
| `email` | `enabled`, host, port, TLS, sender, `username_env`, `password_env` |
| `webhook` | `enabled`, URL, `token_env` |
| `s3` | Bucket, region, endpoint, `public_base_url`, key env names, `photo_key_prefix`, `max_upload_bytes` |
| `rabbitmq` | `enabled`, host, port, vhost, user, `password_env`, exchange, publish timeout, `prefetch` |
| `observability` | `service_name`, `metrics_enabled`, `metrics_port`, `tracing_enabled`, `otlp_endpoint`, `export_timeout_seconds` |
| `integrations` | `credential_key_env`, `request_timeout_seconds`, and **`providers`** — the certified e-invoicing platforms this deployment offers |

**`integrations.providers` is the one section that is a catalogue rather than a
set of dials.** Which platforms an agency may connect to changes when the
registry does — one loses its registration, another publishes an API — so the
list of them, with each platform's display name, documentation link, coverage
and required credential fields, is configuration rather than code. It is the
single statement of who the platforms are: the gallery, the enable dialog and
the transmission service all read it, so a fact about a vendor is written once.
A test asserts that the shipped file still declares every platform there is a
connector for.

Each is a Pydantic model with its own validators and its own `MT*` exception
family, so a malformed value fails at start-up naming the field rather than at
first use naming nothing.

## Secrets

**No password is ever written into a YAML file.** A `*_env` key names the
variable, and the value is read at connection time — so rotating a secret needs
a restart, not a rebuild.

| Variable | Named by | Read at |
|---|---|---|
| `SIMPLE_ERP_CONFIG` | — | start-up |
| `POSTGRES_PASSWORD` | `database.password_env` | connect |
| `JWT_SECRET_KEY` | `auth.jwt_secret_env` | sign / verify |
| `S3_ACCESS_KEY` · `S3_SECRET_KEY` | `s3.access_key_env` · `secret_key_env` | upload |
| `SMTP_USERNAME` · `SMTP_PASSWORD` | `email.username_env` · `password_env` | send |
| `PLANNING_WEBHOOK_TOKEN` | `webhook.token_env` | call / verify |
| `BILLING_WEBHOOK_TOKEN` | `billing_webhook.token_env` | call / verify |
| `EINVOICING_CREDENTIAL_KEY` | `integrations.credential_key_env` | seal / open a platform credential |
| `RABBITMQ_PASSWORD` | `rabbitmq.password_env` | connect |
| `VITE_API_BASE_URL` | — | front-end **build** |

**`EINVOICING_CREDENTIAL_KEY` is the one that cannot be replaced.** Every other
variable here is a credential for something that can be issued again; this one
is the only thing that can read an agency's stored platform credentials back, so
losing it means every agency must re-enter its certified platform's API key. It
belongs in the same backup discipline as the database, and it is read by the API
alone — a worker publishes `bill.paid` and the API's loopback webhook does the
transmission.

Start from `infra/compose/.env.example`, copied to `infra/compose/.env` —
Compose reads it from the directory of the first `-f` file, so one left at the
repository root is silently not read. The development overlay falls back to well-known
defaults; **the production overlay does not** — every variable is `${VAR:?}`
there, so a stack launched without them refuses to start rather than coming up
with `change-me-in-any-real-deployment` as its signing key.

## What the process reports about itself

`observability` is read by all four backend processes.

**Metrics and tracing switch independently.** Metrics are cheap and need nothing
to receive them, so they are on everywhere including a laptop. Tracing needs a
collector, and a process pointed at one that is not there pays a failed
connection on every request — so it is opted into by a deployment that has one.
The endpoint is validated either way, so turning tracing on is one flag rather
than a flag and a debugging session.

**`service_name` is the application's, and each entry point adds what it is** —
`simple-erp-api`, `simple-erp-worker-planning`. Four processes share one image
and one configuration file; naming each in the file would mean four files, or
one file each process had to ignore most of. The *environment* is a label the
deployment adds: putting it here would make "API latency across staging and
production" two series that cannot be compared.

**`metrics_port` is the worker's.** The API serves `/metrics` on the port it
already listens on. The worker had no port at all, which is why it also had no
readiness probe — so Kubernetes reported it Ready the instant the process
started, before it had a database, a broker connection or a single queue bound.

**There is no sampling rate.** It belongs to the collector, which sees every
service's traffic and can decide consistently; a rate set per process produces
traces that are complete for one hop and missing the next, which looks like the
missing service never ran. → [14](14-observability.md)

## Three settings that behave unexpectedly

**`VITE_API_BASE_URL` reaches `npm run dev` and nothing else.** Vite inlines
every `VITE_*` value into the bundle at build time, which is why the built image
no longer uses one: the API's address was inlined into the JavaScript, so one
image existed per environment and a promotion rebuilt rather than promoted — the
digest tested in staging was never the digest that reached production.

A built image reads `/config.json` at start-up instead. It ships in the image
naming the same-origin `/api` that nginx proxies, so a deployment that wants
that needs no configuration at all; one that wants something else mounts over it
(a bind mount in compose, a ConfigMap in the cluster). nginx serves it
`no-store`, because a cached copy would leave a promoted image pointing at the
environment it was promoted *from*.

**`cors_origins` is YAML-only.** There is no `*_env` escape hatch, so deploying
to a new front-end origin means editing the configuration file rather than
setting a variable.

**Most of the `planning` block is a seed.** Six values —
`max_intervention_radius_km`, `day_start_minute`, `day_end_minute`,
`lunch_break_minutes`, `lunch_window_start_minute` and
`lunch_window_end_minute` — populate `PlanningSettings` on first read and
are never consulted again. After that a manager owns them through the API,
and editing the file will not move a running deployment.

The rest of the block is *not* seeded and stays live: the travel speeds,
the solver budget and the objective weights are properties of the road
network and of the search, not agency rules somebody should be changing
from a settings screen. → [06](06-planning-computation.md)

## Three defaults chosen deliberately

**`email.enabled: false`** outside the development overlay, so a developer's
machine never opens an SMTP connection by accident. A disabled service raises
`MTEmailNotConfigured` rather than silently doing nothing.

**`rabbitmq.enabled: false`** in `app.yaml`, so somebody running the API alone is
not blocked by the absence of a broker: a publish that cannot connect is logged
and dropped, and the database still holds every fact the message carried.

**`auth.allow_company_registration: false`** in `app.yaml`, and `true` only in
the development and demonstration overlays. It opens
`POST /api/v1/companies/registration`, which grants its unauthenticated caller
the administrator role — and a company is not yet a tenancy boundary, so that
administrator reads every agency's records rather than only the one they just
founded. A deployment opts in knowingly or not at all. The value must be a
**boolean**: a quoted `"false"` is refused rather than read as true.
→ [11](11-security.md)

## Logging

`backend/conf/logger.yaml` — colourised console plus a rotating
`logs/backend.log`, 10 MB × 7. The worker reads the same file, so its output is
greppable alongside the API's.

Every service and repository takes `logger: Optional[Logger] = None` and defaults
to a logger named after its module, with `%s` lazy formatting. Secrets are never
logged: `DatabaseConfig.dsn_without_password` and
`RabbitMqConfig.url_without_password` exist so a connection failure can name
*which* server without putting the credential in a log file.
