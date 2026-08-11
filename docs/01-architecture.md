# 01 — Architecture

Two questions, one chapter: **how the code is organised**, and **how the
processes talk to each other**. They were two chapters until it became clear
that neither answers a real question on its own — the layer graph explains why
`worker` may not import `api`, and the process map explains what the worker does
instead, and you cannot follow either without the other.

It is long. Read the diagram and **Processes**, then stop; the rest is reference.

| Want | Section |
|---|---|
| What runs, and what talks to what | [The system in one diagram](#the-system-in-one-diagram) · [Processes](#processes) |
| Why the code is arranged as it is | [Layers](#layers) · [Package layout](#package-layout) |
| What a request does | [Request flow](#request-flow) · [The read and write paths](#the-read-and-write-paths) |
| What crosses which wire | [① The event bus](#-the-event-bus) · [② The loopback webhooks](#-the-loopback-webhooks) · [③ SSE](#-sse--the-last-hop-to-the-browser) |
| What it looks like end to end | [Sequences](#sequence-a-planning-run-end-to-end) |
| What happens when something is down | [Failure semantics](#failure-semantics-in-one-table) · [Known gaps](#known-gaps) |

---

## A word on "microservices"

These are **not** microservices, and reading them as such will mislead you.

Five processes run the application, but they share one image, one codebase, one
database and one set of domain models. There is no service boundary, no
per-service schema, no independent deployability of the *domain* — only of the
*work*. What is split is **execution**, not ownership: a CP-SAT solve pins a
core for a minute, a notification fan-out finishes in milliseconds, and one
process cannot be sized for both.

The accurate description is a **modular monolith with asynchronous workers**.
Everything below is easier to follow once that is settled.

---

## The system in one diagram

```
                            ┌──────────────────────────────────────────┐
   browser ──── HTTPS ──────▶ frontend  (nginx, or Vite in development) │
      │                      └──────────────────┬───────────────────────┘
      │                                         │  /api proxied
      │  ③ SSE (long-lived GET, wake-ups only)  │
      └──────────────────────┬──────────────────┘
                             ▼
        ╔════════════════════════════════════════════════════════════╗
        ║  api            FastAPI · uvicorn · port 8000              ║
        ║  · serves REST      · holds every open SSE stream          ║
        ║  · publishes events · receives the two loopback webhooks   ║
        ╚═╤═════════════╤═════════════════╤══════════════╤═══════════╝
          │             │                 │              │
          │ SQL         │ S3              │ ① AMQP       │ ② HTTP (loopback,
          │             │                 │   publish    │    inbound)
          ▼             ▼                 ▼              ▲
    ┌───────────┐ ┌───────────┐   ┌───────────────────┐  │
    │ PostgreSQL│ │  MinIO    │   │ RabbitMQ          │  │
    │ (pgbouncer│ │  photos   │   │ topic exchange    │  │
    │  in prod) │ └───────────┘   │  "simple-erp"     │  │
    └─────▲─────┘                 │ + "simple-erp.dlx"│  │
          │                       └──┬─────┬───────┬──┘  │
          │ SQL                      │     │       │     │
          │        ┌─────────────────┘     │       └──────────────┐
          │        │                       │                      │
    ╔═════╧════════╧═══╗   ╔═══════════════╧═════╗   ╔════════════╧══════╗
    ║ worker-planning  ║   ║ worker-notifications║   ║ worker-billing    ║
    ║ CP-SAT solves    ║   ║ fan-out + email     ║   ║ invoice generation║
    ║ queue:           ║   ║ queue:              ║   ║ queue:            ║
    ║  planning-runs.* ║   ║  quote-notifications║   ║  billing-runs.*   ║
    ╚══════════════════╝   ╚═══════════╤═════════╝   ╚═══════════════════╝
                                       │ SMTP
                                       ▼
                                  ┌─────────┐
                                  │ Mailpit │  (dev)  ·  real MTA in production
                                  └─────────┘

    migrate — one-shot, runs Alembic to head and exits. Everything waits for it.
```

Four channel kinds, numbered above and detailed below:

| | Channel | Between | Shape |
|---|---|---|---|
| ① | **AMQP** (RabbitMQ) | api → workers, workers → workers | Durable, at-least-once, identifiers only |
| ② | **HTTP loopback** ("webhook") | worker → api | Fire-and-forget, single attempt |
| ③ | **SSE** | api → browser | Long-lived, content-free wake-ups |
| — | **REST** | browser → api | Ordinary request/response, bearer auth |

Plus three egress paths that are not inter-process: **SQL** to PostgreSQL,
**S3** to MinIO, **SMTP** to the mail relay.

---

## Processes

| Process | Entry point | What it does | Consumes | Publishes | Scales on |
|---|---|---|---|---|---|
| **migrate** | `["migrate"]` | Alembic to `head`, once, then exits. Everything else waits for it | — | — | Runs once |
| **api** | `["api"]` | Serves HTTP and holds the SSE connections | `notification.created.*` | 8 keys (below) | CPU (HPA) |
| **worker-planning** | `["worker", "planning"]` | The CP-SAT solves | `planning.run.requested.*` | `planning.run.completed` | `planning-runs` depth (KEDA) |
| **worker-notifications** | `["worker", "notifications"]` | Notification fan-out and email | 7 keys | `notification.created` | `quote-notifications` depth |
| **worker-billing** | `["worker", "billing"]` | Invoice generation | `billing.run.requested.*` | `billing.run.completed` | `billing-runs` depth |
| **frontend** | nginx / Vite | The bundle, and the `/api` proxy | — | — | Replicas |

And three things it depends on rather than runs: `postgres:17-alpine` for
everything durable, `minio/minio` for photographs and documents,
`rabbitmq:4-management` for the events.

**One image, five entry points.** Building one image and running it five ways is
what stops them drifting apart — which is exactly what happens once a worker
gets a Dockerfile of its own.

**Exactly one process migrates, and it is not the API.** `alembic upgrade head`
used to be the first half of the API container's start command, which is fine
with one replica and a race with two — how a deployment ends up half-upgraded.
It is now its own entry point: a one-shot `migrate` service in compose, and a
`pre-install,pre-upgrade` hook Job in the chart. The same arrangement described
twice, rather than two that have to agree.

### Why the worker is three deployments

They are unlike each other in the way that matters to a scheduler.

| Role | Shape of the work |
|---|---|
| `planning` | **CPU-bound**, pins its cores for a thirty-second budget |
| `notifications` | **I/O-bound and quick**, finishes in milliseconds |
| `billing` | **I/O-bound and long** — a monthly close is hundreds of renders and uploads, minutes at a time, and zero the rest of the month |

In one process they scale together — so a manager waits half a minute to be told
a quote needs looking at, because the pod is mid-solve. Put billing on the
notifications role and the same failure reappears one level up: a monthly close
would sit at the head of `quote-notifications` for minutes with every badge
queued behind it. Put it on planning and it contends with the solve and inherits
a replica count tuned for solve latency, when its own queue depth spikes once a
month.

Split, each scales on its own queue's depth, gets its own resources, and can be
put on its own node pool.

**No role owns the control plane.** `company.created` is consumed by *all three*,
each on an exclusive queue of its own, because each has queues to declare when an
agency is founded. Making it a fourth deployment would hand each announcement to
one process and leave the others serving every agency but the new one.

---

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

Beside them sits one thing that is **not** a member: `backend/integrations/`,
the outbound clients for the certified e-invoicing platforms. It is a plain
module — no `pyproject.toml`, no `src` layout — shipped by the workspace root
itself, because it is four HTTP clients imported by `service` and by nothing
else, and a distribution boundary around them bought a lockfile entry and a
build target for isolation nobody used. It is kept outside `service` all the
same: these are I/O against APIs somebody else versions, and a change of
supplier should be replaceable without touching a domain rule.

**The worker does not depend on `api`**, deliberately. A background consumer
that pulled in FastAPI and uvicorn to read one YAML file would make the graph a
ring; it duplicates fifteen lines of logging setup instead, and the duplication
is documented where it sits. It is also the reason the loopback webhooks exist
at all — see [②](#-the-loopback-webhooks).

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
no holder is not a record anybody keeps, and neither is a skill.
`models/planning` is grouped the same way, around `intervention/`,
`planning_run/` and `hca_planning/`, and `schemas/requests` and
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

---

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

---

## ① The event bus

A single **topic** exchange, `simple-erp`, durable. Every routing key is shaped

```
<event>.<company_id>
```

with the agency **last**, so one binding can select a single agency
(`quote.submitted.<id>`) or all of them (`quote.submitted.*`). An empty company
id raises rather than producing `quote.submitted.`, which is a valid key that
binds to nothing.

The API answers **202** to a planning or billing request and publishes; the
worker consumes, does the work, and stores the result. The message is
acknowledged only once the handler returns, so a worker killed mid-solve leaves
the message for the next one. That replaced FastAPI `BackgroundTasks`, which
lost the run entirely on a restart and occupied a web worker for the thirty
seconds a solve takes.

### Topology

```
                              exchange: simple-erp (topic, durable)
                                            │
   ┌────────────────────────────────────────┼──────────────────────────────┐
   │                    │                   │                │             │
planning.run.        quote.submitted.*   notification.    billing.run.  company.
 requested.*         quote.validated.*    created.*        requested.*  created.*
   │                 quote.refused.*        │                │             │
   │                 skill.added.*          │                │             │
   │                 planning.run.          │                │             │
   │                  completed.*           │                │             │
   │                 billing.run.           │                │             │
   │                  completed.*           │                │             │
   │                 bill.accepted.*        │                │             │
   ▼                      ▼                 ▼                ▼             ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────┐  ┌─────────────┐  ┌────────┐
│planning-runs │  │quote-notification│  │exclusive │  │billing-runs │  │exclusive│
│  .<company>  │  │   s.<company>    │  │ per API  │  │ .<company>  │  │per role│
│quorum,durable│  │ quorum, durable  │  │ replica  │  │quorum,durabl│  │        │
└──────┬───────┘  └────────┬─────────┘  └────┬─────┘  └──────┬──────┘  └────────┘
       │                   │                 │               │
   worker-planning   worker-notifications  api (SSE)   worker-billing
       │                   │                                 │
       └───────────────────┴──── on handler raise ───────────┘
                                   │ requeue=False
                                   ▼
                    exchange: simple-erp.dlx (topic, durable)
                                   │
                    planning-runs.dlx / quote-notifications.dlx
                    billing-runs.dlx      — one per role, not per agency
```

### Queue settings, and why

| Setting | Value | Why |
|---|---|---|
| `x-queue-type` | `quorum` | Survives a broker node loss; cannot be changed after declaration |
| `x-delivery-limit` | `5` | Caps a message that *kills* its consumer — poison-pill protection |
| `x-dead-letter-exchange` | `simple-erp.dlx` | A raising handler dead-letters immediately |
| `prefetch` | `1` | A solve pins a core for its whole budget; a second message would queue behind it inside the process |
| ack | on handler **return** | `requeue=False`, so a raise dead-letters rather than looping |

A Prometheus alert fires on **any** DLQ depth — a dead-lettered message is
always a human's problem.

### Who publishes what

| Key | Published by | Payload |
|---|---|---|
| `planning.run.requested` | `POST /planning/runs`, intervention deletion, replan helper | `run_id`, `company_id` |
| `planning.run.completed` | worker-planning, after the solve | `run_id`, `status`, `company_id` |
| `quote.submitted` | `POST /me/quotes/{id}/submit` | `quote_id`, `reference`, `author_id`, … |
| `quote.validated` / `quote.refused` | the manager's decision routes | `quote_id`, `reference`, `author_id`, … |
| `skill.added` | `POST /me/hca/skills` | `hca_id`, `skill_code`, … |
| `billing.run.requested` | `POST /bills/runs` | `run_id`, `company_id` |
| `billing.run.completed` | worker-billing | `run_id`, `status`, `company_id` |
| `bill.accepted` | `POST /bills/{id}/accept` | `bill_id`, `company_id` |
| `company.created` | self-registration, the seeder | `company_id`, `name` |
| `notification.created` | worker-notifications, after every fan-out | `recipient_ids` |

**Identifiers, never records.** A message says *what happened to which row*, and
the handler reads the row. A payload carrying the record would be a second copy
of the truth, stale by the time it is read.

`company_id` rides in the payload **as well as** the routing key, because the
broker consumes the key before the handler ever sees the message.

### The one rule that shapes everything

> **A failed publish never fails the request that caused it.**

`EventPublisher.publish` logs and returns `False` on every failure path —
broker disabled, unreachable, or the publish itself throwing. The database
already holds the fact; only the push is lost. A quote stays in
`pending-validation` where the manager's queue reads it anyway; a planning run
stays `pending` and can be re-queued.

Consumers are the mirror image: `EventConsumer.start()` deliberately does *not*
catch, so a worker that cannot reach the broker **crashes** and is restarted,
rather than sitting healthy and idle while its queue fills.

→ [05 — Events and notifications](05-events-and-notifications.md) for the
message shapes and the handler-by-handler detail.

---

## ② The loopback webhooks

Two of them — `planning-completed` and `bill-accepted` — and neither is an
integration with anything external. **The app calls its own endpoint.**

```
worker-notifications ──POST /api/v1/webhooks/planning-completed──▶ api
                        header: X-Webhook-Token: <shared secret>       │
                        body:   {"run_id": "..."}                      │
                                                                       ▼
                                                      loads run, resolves requester,
                                                      emails diaries to assistants
                                                      and quotes to customers
```

The reason is dependency direction. The worker has no `api` dependency and no
request context, but sending diaries and invoices is heavy work that wants the
API's handlers, logging and failure reporting. So the worker hands the run back
over HTTP and the API does the dispatch as an ordinary request.

Describe it as a **loopback dispatch trigger**, not an integration.

| Property | Value |
|---|---|
| Auth | Static shared secret, `compare_digest` on receipt. **No HMAC, no timestamp, no replay protection** |
| Retry | None — one attempt |
| Timeout | `timeout_seconds`, 10s default / 30s deployed |
| Failure | Swallowed, logged, returns `False`. Never fails the run |
| Bearer middleware | `/api/v1/webhooks/` is exempt; the token *is* the auth |

---

## ③ SSE — the last hop to the browser

The stream carries **no content**. A notification arrives as a bare frame and
the browser refetches over REST. That keeps authorisation entirely in the REST
layer: the stream can never leak something the recipient could not already GET.

```
worker-notifications                api replica A          api replica B
        │                                 │                      │
   writes rows (committed)                │                      │
        │                                 │                      │
   publishes notification.created.<co>    │                      │
        └──────────► RabbitMQ ────────────┼──────────────────────┤
                        │                 │                      │
             each replica has its OWN     ▼                      ▼
             exclusive queue bound   NotificationStreams   NotificationStreams
             to notification.created.*   registry              registry
                                          │                      │
                                    wake queue(recipient)   (no reader here)
                                          │
                                    event: notification
                                    data: {}
                                          ▼
                                      browser  ──▶ refetches over REST
```

**Why an exclusive queue per replica.** A shared durable queue would hand each
announcement to *one* API pod while the readers connected to the others slept.
Fan-out to every pod is the requirement; each declares its own server-named,
exclusive, auto-deleted queue bound to the same key.

### Two details that look odd until you see the constraint

**A separate 60-second stream token.** `EventSource` cannot set an
`Authorization` header, so the credential must go in the URL — and URLs leak
into referrers, proxy logs and history. A 12-hour session token there would be a
real exposure; a 60-second one scoped `stream` is not. The scope is enforced
both ways: a stream token is refused by the normal API path, and a session token
is refused by the stream.

**The client bypasses `EventSource`'s own retry.** Built-in retry replays the
*same URL*, whose token is dead after a minute — it would reconnect forever with
a corpse. `onerror` closes the source and reconnects with a freshly minted token
after 5s; failure to mint backs off to 15s.

A `ready` frame on every connect doubles as a catch-up signal, which is why
there is no polling interval behind the unread badge. Keep-alive comments every
20s stop proxies closing an idle stream at 60 — matched by `proxy_read_timeout
3600s` in nginx and the ingress annotations.

---

## Sequence: a planning run, end to end

The richest path in the system — it uses every channel.

```
browser        api            RabbitMQ      worker-planning   worker-notif      PostgreSQL
   │            │                 │               │                │                │
   │ POST /planning/runs          │               │                │                │
   ├───────────▶│  record run (pending) ──────────┼────────────────┼───────────────▶│
   │            │ publish planning.run.requested  │                │                │
   │            ├────────────────▶│               │                │                │
   │◀───202─────┤                 ├──────────────▶│                │                │
   │            │                 │          claim run             │                │
   │            │                 │          load quotes ──────────┼───────────────▶│
   │  poll GET /planning/runs     │          SOLVE (per day,       │                │
   ├───────────▶│                 │           concurrent)          │                │
   │            │                 │          store interventions ──┼───────────────▶│
   │            │                 │          partial? → feedback + │                │
   │            │                 │            quote → pending-val ┼───────────────▶│
   │            │                 │◀── publish planning.run.completed               │
   │            │                 ├───────────────────────────────▶│                │
   │            │                 │                          succeeded? ──────┐     │
   │            │                 │                          failed? notify   │     │
   │            │                 │                                │         │     │
   │            │◀─── POST /webhooks/planning-completed ────────────┘         │     │
   │            │  emails diaries + quotes (SMTP)                             │     │
   │            │                 │◀── publish notification.created ──────────┘     │
   │            │◀────────────────┤                                                 │
   │◀── SSE wake-up ──────────────┤                                                 │
   │  refetch ──▶│                                                                  │
```

Note the **two hops** after the solve: planning publishes *completed*, and it is
the **notifications** worker that both fires the webhook and writes the
notification rows. The solving process does neither.

Note also that a **partial** run writes its plan, annotates the affected quotes
with why their work would not fit plus free alternative slots, and returns them
to `pending-validation` — so the operator's next action is on the quotes screen,
not the planning screen.

## Sequence: a quote submitted for validation

```
assistant      api          RabbitMQ     worker-notifications      manager's browser
   │            │               │                 │                        │
   │ POST /me/quotes/{id}/submit│                 │                        │
   ├───────────▶│ status → pending-validation     │                        │
   │            │ publish quote.submitted.<co>    │                        │
   │            ├──────────────▶├────────────────▶│                        │
   │◀── 200 ────┤               │        resolve supervisors FROM ROLES     │
   │            │               │        write one row per recipient        │
   │            │               │◀── publish notification.created           │
   │            │◀──────────────┤                 │                        │
   │            ├─── SSE wake-up ─────────────────┼───────────────────────▶│
   │            │◀── GET /notifications/unread-count ─────────────────────┤
```

**Recipients are resolved worker-side, from roles — never named by the message.**
A payload that named its own recipients would be an arbitrary-send primitive:
anything able to publish could notify anybody.

## Sequence: billing

```
manager     api        RabbitMQ    worker-billing   worker-notifications
   │         │             │             │                  │
   │ POST /bills/runs      │             │                  │
   ├────────▶│ publish billing.run.requested                │
   │         ├────────────▶├────────────▶│                  │
   │◀─ 202 ──┤             │      generate invoices ────────┼──▶ PostgreSQL
   │         │             │◀── publish billing.run.completed│
   │         │             ├─────────────────────────────────▶│
   │         │             │                    notify supervisors: bills to validate
   │         │             │                                  │
   │ POST /bills/{id}/accept                                  │
   ├────────▶│ publish bill.accepted                          │
   │         ├────────────▶├─────────────────────────────────▶│
   │         │             │              POST /webhooks/bill-accepted ──▶ api
   │         │             │                                  │     emails the invoice
```

Billing mirrors planning exactly: a **request** key consumed by its own role, a
**completed** key consumed by notifications, and a loopback webhook for the
document dispatch.

---

## Failure semantics, in one table

| What breaks | Effect | Recovery |
|---|---|---|
| Broker down, API publishing | Request still succeeds; push lost | Row is committed; re-queue manually |
| Broker down, worker starting | Worker **crashes** | Supervisor restarts it |
| Broker down, API relay | Logged; API serves on | No live pushes; next REST fetch shows all |
| Worker crashes mid-handle | Message never acked → redelivered | Session rolled back; starts clean |
| Handler raises | Dead-lettered immediately (`requeue=False`) | Alert on DLQ depth |
| Poison pill (kills process) | Broker dead-letters after 5 deliveries | Alert on DLQ depth |
| Webhook fails | Logged, swallowed | **No email is sent, and the run still reports success** |
| SSE dropped (deploy, proxy) | Stream severed | Client reconnects in 5s, `ready` triggers refetch |
| PostgreSQL down | Requests fail loudly | — |

---

## Data stores

| Store | Holds | Written by |
|---|---|---|
| **PostgreSQL** | Everything durable: quotes, assistants, customers, interventions, planning runs, notifications, bills | api + all three workers |
| **MinIO / S3** | Assistant photographs, account portraits, company logos, invoice documents | api + worker-billing |
| **RabbitMQ** | In-flight events; nothing durable that matters | api + workers |

**One database, shared.** There is no per-service schema and no service
boundary — see the note at the top. Multi-tenancy is by `company_id` column,
not by database.

In production the API reaches PostgreSQL through **pgbouncer**; the workers hold
their own pool and open one session per message, so a crash mid-handle rolls
back to a known state.

---

## The observability plane

```
   api ─┐                                   ┌──▶ Prometheus ──┐
        ├── /metrics (scrape) ──────────────┤                 │
workers ┘   worker port 9100                │                 ├──▶ Grafana
                                            │                 │
   api ─┐                                   │                 │
        ├── OTLP traces ──▶ otel-collector ─┴──▶ Tempo ───────┤
workers ┘                        │                            │
                                 └──────────▶ (fan-out point) │
                                                              │
   all containers ── stdout JSON ──▶ Alloy ──▶ Loki ──────────┘
```

The collector is **the only tracing address the application knows**. Fan-out to
Tempo — and to anything added later — happens inside it, so the app never learns
a second endpoint.

---

## Deployment topologies

**Compose** (development): every process plus PostgreSQL, MinIO, RabbitMQ,
Mailpit and the full observability chain. `docker-compose.yaml` is never run
alone — an overlay says how you want it.

**Kubernetes** (production): the migration is a `pre-install,pre-upgrade` hook
Job so exactly one process migrates and everything waits for it. The API
autoscales on CPU; each worker autoscales on **its own queue's depth** via KEDA,
because a consumer waiting on a broker burns no CPU and a CPU autoscaler would
never scale it.

**The chart is one workload short.** It ships `api`, `frontend`,
`worker-planning`, `worker-notifications` and the migration Job — and **no
`worker-billing`**. The word "billing" does not appear anywhere in
`infra/chart/`. Compose runs the role; Kubernetes does not.

| Process | Compose | Helm chart |
|---|---|---|
| migrate | ✅ one-shot service | ✅ hook Job |
| api | ✅ | ✅ + HPA |
| worker-planning | ✅ | ✅ + KEDA |
| worker-notifications | ✅ | ✅ + KEDA |
| **worker-billing** | ✅ | ❌ **missing** |
| frontend | ✅ | ✅ |

The chart refuses to render on configurations that are silently wrong at
runtime — worker threads not matching the CPU limit, a wall-clock net too tight
to spend its budget, a termination grace period shorter than a solve.

---

## Known gaps

Recorded because a schema that shows only what works is a sales diagram.

- **Both webhooks are disabled by default outside development.** `enabled:
  false` in `app.yaml`, `app.docker.yaml` and the chart. With three silent gates
  in a row — disabled, token unset, HTTP error swallowed — an unmodified
  production deployment sends **no planning or invoice emails at all**, with a
  debug line as the only trace.
- **`notification_stream_clients` is declared but never incremented.** The alert
  `NoServerSentEventReadersAtAll` fires on `sum(...) == 0`, so as written it
  fires permanently.
- **The webhook secret is a bare shared token.** No signature, no timestamp, no
  replay protection — acceptable for a loopback call inside one network, and not
  something to expose beyond it.
- **Billing does not run in Kubernetes.** The chart has no `worker-billing`
  deployment, so nothing declares `billing-runs.<company>` and nothing binds
  `billing.run.requested.*`. The API would publish the event, the exchange would
  match no binding, and the message would be **dropped silently** — no queue
  depth to alert on, no dead letter, no error. Invoices would simply never be
  generated, and the run would sit `pending` for ever. Either add the workload
  or disable the billing routes in that environment.
- **`run_planning_job`** in `api/dependencies.py` is the legacy in-process
  `BackgroundTasks` path the worker replaced. It has no production caller.

---

## Where to read next

| Question | Chapter |
|---|---|
| What exactly crosses the bus, and the message shape | [05 — Events and notifications](05-events-and-notifications.md) |
| How the solver decides, and what a partial run means | [06 — Planning computation](06-planning-computation.md) |
| Every setting and secret named above | [08 — Configuration](08-configuration.md) |
| The house style a change is reviewed against | [12 — Conventions](12-conventions.md) |
| What scales on what, and the measured ceilings | [13 — Kubernetes](13-kubernetes.md) |
| What is alerted on | [14 — Observability](14-observability.md) |
