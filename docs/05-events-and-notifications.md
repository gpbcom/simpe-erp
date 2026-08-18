# 05 — Events and notifications

## The path an event takes

```
  assistant clicks Submit
        │
        ▼
  API   store the quote as pending-validation      ← durable, synchronous
        publish quote.submitted                    ← best effort
        │
        ▼
  RabbitMQ  exchange simple-erp (topic, durable)
        │
        ├──▶ queue quote-notifications ──▶ worker-notifications
        │                                     writes one Notification per
        │                                     supervisor, then publishes
        │                                     notification.created
        │
        └──▶ queue planning-runs ───────▶ worker-planning
                                              runs the CP-SAT solve
        │
        ▼
  API   per-instance exclusive queue ──▶ NotificationStreams ──▶ SSE ──▶ browser
        │                                (a signal, carrying no data)
        ▼
  browser  refetches GET /api/v1/notifications             ← where the news lives
```

**Two classes and two deployments.** `WorkerRunner` is everything a worker
consumes and everything it does; which half it does is decided by its
`WorkerRole` — `worker planning` or `worker notifications`, one image, two
Deployments. `NotificationStreams` is every reader an API instance is holding
and the framing they are served. There is no notification service and no
separate handler object between them — a passthrough over `NotificationRepository`
and a callback the runner had to hand back to its own handlers, respectively.

## Topology

One durable topic exchange, `simple-erp`. **Quorum** queues, publisher
confirms, manual acknowledgement, `prefetch=1`, and a `simple-erp.dlx`
dead-letter exchange.

**Every routing key ends in an agency**, and every queue is that agency's own.
`EventRoutingKey` holds the *event* half. The whole key is
`<event>.<company_id>`, built by `scoped_to()`.

| Routing key | Queue | Consumer | Effect |
|---|---|---|---|
| `quote.submitted.<company>` | `quote-notifications.<company>` | worker-notifications | A notification per manager and admin of the agency |
| `quote.validated.<company>` | `quote-notifications.<company>` | worker-notifications | A notification for the author |
| `quote.refused.<company>` | `quote-notifications.<company>` | worker-notifications | A notification for the author |
| `planning.run.requested.<company>` | `planning-runs.<company>` | worker-planning | Runs the solve |
| `planning.run.completed.<company>` | `quote-notifications.<company>` | worker-notifications | Notifies supervisors — **only on failure** |
| `skill.added.<company>` | `quote-notifications.<company>` | worker-notifications | Notifies every manager and admin that somebody declared a skill |
| `company.created.<company>` | exclusive, per worker | **both** roles | Binds the new agency's queues |
| `notification.created.<company>` | exclusive, per API instance | **API** | Wakes the readers that instance holds |

`skill.added` is the one topic here raised by a **subordinate** rather than by
the quote workflow or the solver, and it is what makes a self-declared skill
safe to take effect without approval. Somebody adding one silently widens what
the planner may send them to. The notification is what leaves a supervisor able
to challenge it before the next run acts on it. It carries no `quote_id`, which
is why `NotificationKind.concerns_a_quote` had to stop being written as "not
the planning one" — a skill notification rendered as a link would be a dead
one.

**Two queues, not one, and then one set per agency.** A solve pins a core for
thirty seconds; sharing a queue with the notification fan-out would leave a
manager waiting half a minute to be told a quote needs looking at. Splitting
again by agency means one agency's backlog or poison message is its own, rather
than something every other agency waits behind.

### Quorum, and why it cannot be changed later

RabbitMQ 4 **removed** mirrored queues. A durable *classic* queue on a cluster
therefore lives on exactly one node and goes with it, taking every planning run
nobody had picked up yet — and durability and replication look identical in a
single-node development stack, which is where the arrangement was written.

The queues are declared `x-queue-type: quorum`, replicated by Raft, with an
`x-delivery-limit`. That limit is protection against a message that poisons the
*process* rather than the handler: a handler that raises already dead-letters,
but one that is **killed** — an out-of-memory solve — never returns to reject
anything, and without a limit the broker redelivers it for ever, taking a worker
down on each attempt.

**Redeclaring an existing classic queue as quorum is a `PRECONDITION_FAILED`,
not an upgrade.** A deployment that ran on classic queues needs them drained and
deleted once, which is why it was done while there was at most one deployment to
drain.

### One dead-letter queue per role, not per agency

The per-agency arrangement read well and did not scale: at a few hundred
agencies it is a few hundred extra queues, each a Raft cluster of its own,
holding failures that arrive at a rate of nearly none.

There is now one per role — `planning-runs.dlx`, `quote-notifications.dlx` —
bound to that role's own topics across every agency rather than to `#`. The
exchange is shared between the roles, so a catch-all binding would put planning
failures and notification failures in one queue and leave a reader unable to
tell which worker had given up on what. The agency is still the last field of
every routing key, so one agency's failures remain one selector away.

**`company_id` is a required parameter of `publish()`, with no default.** It
decides which agency's queue a message lands in, so a default would mean a
forgotten argument still publishes — to the wrong agency, or to a key nothing is
bound to. A missing one is a `TypeError` at the call site instead. Scoping to an
empty identifier raises `MTRoutingKeyMissingCompany` rather than producing
`quote.submitted.`, which is a valid topic key that binds to nothing.

**The agency goes last in the key.** A binding can then select one agency by
suffix, or every agency with `*`. Putting it first would make "every event for
this agency" easy and "this event for every agency" impossible — and the worker
needs the second one.

### A newly founded agency

Self-registration creates agencies while the workers are running, so the workers
have to notice. Founding one publishes `company.created.<id>`; every worker
binds `company.created.*` on an **exclusive, server-named** queue and declares
the new agency's queues on receipt. Exclusive matters: a durable shared queue
would hand each announcement to exactly one worker, and the others would run on
serving every agency but that one.

Each worker also enumerates the agencies at startup, which is what makes the
announcement queue safe to be non-durable — anything missed while a worker was
down is picked up next time it starts. The announcement is bound *before* the
enumeration runs, so an agency founded in between cannot fall through the gap;
declaring a queue twice is harmless, leaving a gap is not.

If the broker is unreachable when an agency is founded, the agency is still
created and the publish is logged as a warning. The workers pick it up by
enumeration, which is exactly the case enumeration covers.

**`prefetch=1`** because the heaviest consumer is that solve. Taking a second
message while the first is solving would not make it finish sooner.

**A successful planning run notifies nobody.** It rewrites calendars everybody
can see, and telling three managers about every routine weekly run trains them
to ignore the badge — which is what makes them miss the failure that matters.

## The message

Every message is an `EventEnvelope`: a routing key, a payload, and when the
event happened. A consumer can log, retry and dead-letter one without
understanding it; only the handler that claims a routing key looks inside.

The payload carries **identifiers, not records**. A message naming quote `q-1`
is still correct when the consumer reads it a minute later. A message carrying a
copy of the quote is a snapshot that may already be wrong, and the consumer
would have no way to tell.

`occurred_at` is when the *event* happened, not when it was handled. A queue
that backed up overnight must not make yesterday's submissions look like this
morning's.

`envelope.string_field(name)` returns `None` for both a missing field and a
malformed one — which is what a handler wants either way, and stops every
handler repeating the same three checks.

### The one field that is not about the event

`traceparent` carries W3C trace context across the broker. Every instrumentation
library propagates it over HTTP and **none of them does it over a broker**, so
without this a trace stops at `POST /api/v1/planning/runs` — and the thirty
seconds that actually matter are attributed to nothing.

It is **nullable**, because a queue is not drained the instant a deployment
lands: messages written by the previous version are still in it, and a required
field would dead-letter every one of them.

A malformed one is **refused** rather than dropped. Extracted leniently it would
be ignored and a *new* trace begun, so the solve appears to have started on its
own with no request behind it — which reads as a complete picture, and is the
reason that is worse than no trace at all. The check is the specification's own
shape: four hyphen-separated fields, lower-case hexadecimal, and neither
identifier all zeroes.

## Acknowledgement and failure

**A message is acknowledged only once its handler returns.** A worker killed
mid-solve leaves it unacknowledged and the broker redelivers it. Acknowledging
on receipt would lose the planning run entirely — the failure the move off
`BackgroundTasks` was meant to end.

**A handler that raises rejects without requeuing**, so the message
dead-letters rather than spinning. A message that fails once will usually fail
again, and a poison message retrying at full speed is how a broker outage
becomes a database outage.

**A record that no longer exists is logged and acknowledged**, not
dead-lettered. A quote deleted between submission and handling is not an error,
and retrying it forever would never succeed.

Each handler opens its own session and closes it before returning: a solve runs
for thirty seconds, and holding a pooled connection across that per in-flight
message buys nothing.

## When the broker is down

**`EventPublisher.publish` never raises.** It logs at ERROR and returns `False`.

That is the contract the whole design rests on. A quote is submitted whether or
not the broker was reachable; refusing the submission because a notification
could not be queued would turn an outage of a convenience into an outage of the
product. What is lost is the *push* — the quote is in the database in
`pending-validation`, which is where the manager's queue reads it from.

For a planning run the same applies: the run stays `pending` and can be
re-queued, and the identifier the caller polls is real either way.

The publisher forgets its channel after a failure, so the next publish
reconnects rather than failing against a socket that has already gone.

## Notifications

**One row per recipient, not one per event.** Read state belongs to a person,
and two managers must be able to disagree about whether they have dealt with
something.

**Recipients are resolved from roles, in the worker.** The thing publishing an
event knows a quote was submitted. It does not know who is allowed to rule on
it. A caller naming its own recipients would be a way to send a notification to
anybody.

**A fan-out with no agency writes nothing.** `list_supervisors(None)` means
*every* supervisor of *every* agency, so a message that lost its `company_id`
would put a badge on every manager on the platform, naming work they have no
access to. The absence is refused rather than interpreted. This is why
`quote.validated`, `quote.refused` and `planning.run.completed` carry
`company_id` in the **payload** as well as the routing key: the key chooses the
queue and is gone by the time a handler reads the message.

`UserRepository.list_supervisors` returns **managers and administrators**, both,
and excludes inactive accounts. Reaching only managers would silently skip an
agency run by one administrator alone, which is most small agencies. An agency
with no active supervisor is logged at ERROR and produces nothing — work is
piling up with nobody able to release it, and that deserves to be loud.

## Reaching the browser

`EventSource` cannot set an `Authorization` header, so the stream has to
authenticate through the URL. Putting the twelve-hour session token there would
leak it into referrer headers, proxy logs and browser history.

Instead: `POST /api/v1/auth/stream-token` returns a **60-second token carrying
`scope: "stream"`**. `read_subject` refuses it everywhere else, and
`resolve_stream_token` refuses a session token — the scope is checked in both
directions, because a credential that works in two places is two places it can
leak from.

`NotificationStreams` is an **in-process** fan-out: one `asyncio.Queue` per
connected client, held by the API process. Another process cannot write to those
sockets, so there is nothing to gain from distributing the fan-out itself. What
crosses processes is the broker message, which every API instance receives on an
exclusive queue of its own and turns into wake-ups for the readers it happens to
hold. A shared durable queue would hand each message to one instance while the
readers on the others were never woken.

### A frame carries no data

`event: notification` with an empty `data: {}`. It says only that something
changed. The reader then fetches what changed from
`GET /api/v1/notifications`.

That is a deliberate constraint rather than an omission. It keeps one source of
truth instead of two that can disagree. It means a notification is never
delivered by a route that cannot also replay it after a logout. It lets the
broker message carry recipient identifiers rather than records, in keeping with
the rule above. And it means the API pushes without reading the database at all.

A reader that already has a wake-up pending is skipped rather than queued behind
— the wake-ups are indistinguishable, so a second would only produce a duplicate
refetch. That is why the queue holds one.

### Why losing a frame is survivable

**The row is written before anything is pushed** — and after the session that
wrote it has committed, so a reader that acts on the announcement finds the rows
already there.

A reader who was offline finds the notification waiting. There is no poll behind
the stream: the stream announces `ready` on connect **and on every reconnect**,
and the client refetches on it, so a stream that died over lunch catches up the
moment it comes back rather than up to a minute later.

**Signing out and signing back in changes nothing.** A notification is a row
keyed by the account, not per-session state. The only thing that ends its unread
life is the reader marking it. A fresh sign-in reaches the same table through the
same query, and the bell refetches when it mounts.

The stream sends a keep-alive comment every twenty seconds, because proxies
close idle connections and a quiet afternoon is the normal case. nginx is
configured with `proxy_buffering off` for that path; buffering would hold every
frame until the connection closed, turning a live feed into one long silence.

## Where this is tested

| | |
|---|---|
| Publisher, envelope, never-raises | `tests/service/test_event_publisher.py` |
| Worker topology: what is bound, start/stop ordering | `tests/worker/test_worker_runner.py` |
| Fan-out, the announcement, the cross-tenant guard | `tests/worker/test_notification_handlers.py` |
| Wake-ups, the relay, the frames | `tests/api/test_notification_streams.py` |
| The five endpoints, incl. the 404 and persistence | `tests/api/test_notification_endpoints.py` |
| Rows, paging, read state, per-account isolation | `tests/storage/test_notification_repository.py` |
| Email really sent and really received | `tests/integration/test_email_delivery.py` (Mailpit) |
| Badge rises after a real round trip | `qa/robot/suites/05_quote_validation_journey.robot`, `07_notifications.robot` |
