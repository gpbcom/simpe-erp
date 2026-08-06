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
  RabbitMQ  exchange rt-erp (topic, durable)
        │
        ├──▶ queue quote-notifications ──▶ worker  writes one Notification per supervisor
        │                                          publishes notification.created
        │
        └──▶ queue planning-runs ───────▶ worker   runs the CP-SAT solve
        │
        ▼
  API   per-instance exclusive queue ──▶ NotificationBroadcaster ──▶ SSE ──▶ browser
```

## Topology

One durable topic exchange, `rt-erp`. Durable queues, publisher confirms, manual
acknowledgement, `prefetch=1`, and a `rt-erp.dlx` dead-letter exchange.

| Routing key | Queue | Consumer | Effect |
|---|---|---|---|
| `quote.submitted` | `quote-notifications` | worker | A notification per manager and admin of the company |
| `quote.validated` | `quote-notifications` | worker | A notification for the author |
| `quote.refused` | `quote-notifications` | worker | A notification for the author |
| `planning.run.requested` | `planning-runs` | worker | Runs the solve |
| `planning.run.completed` | `quote-notifications` | worker | Notifies supervisors — **only on failure** |

**Two queues, not one.** A solve pins a core for thirty seconds; sharing a queue
with the notification fan-out would leave a manager waiting half a minute to be
told a quote needs looking at, behind work that has nothing to do with them.

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
is still correct when the consumer reads it a minute later; a message carrying a
copy of the quote is a snapshot that may already be wrong, and the consumer
would have no way to tell.

`occurred_at` is when the *event* happened, not when it was handled. A queue
that backed up overnight must not make yesterday's submissions look like this
morning's.

`envelope.string_field(name)` returns `None` for both a missing field and a
malformed one — which is what a handler wants either way, and stops every
handler repeating the same three checks.

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

**Recipients are resolved from roles, in the service.** The thing publishing an
event knows a quote was submitted; it does not know who is allowed to rule on
it. A caller naming its own recipients would be a way to send a notification to
anybody.

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

`NotificationBroadcaster` is an **in-process** fan-out: one `asyncio.Queue` per
connected client, held by the API process. Another process cannot write to those
sockets, so there is nothing to gain from distributing the fan-out itself. What
crosses processes is the broker message, and each API replica pushes to whichever
readers it happens to hold.

A queue that fills is drained of its **oldest** frame rather than blocking the
publisher. One reader on a bad connection must not hold up every other reader,
and the frame it loses is still in the database behind it.

### Why losing a frame is survivable

**The row is written before anything is pushed.** A reader who was offline finds
the notification waiting; the client also polls the unread count every sixty
seconds behind the stream. That is what lets the broadcaster stay simple — it is
an accelerator, not a delivery guarantee.

The stream sends a keep-alive comment every twenty seconds, because proxies
close idle connections and a quiet afternoon is the normal case. nginx is
configured with `proxy_buffering off` for that path; buffering would hold every
frame until the connection closed, turning a live feed into one long silence.

## Where this is tested

| | |
|---|---|
| Publisher, envelope, never-raises | `tests/service/test_event_publisher.py` |
| Email really sent and really received | `tests/integration/test_email_delivery.py` (Mailpit) |
| Badge rises after a real round trip | `qa/robot/suites/05_quote_validation_journey.robot`, `07_notifications.robot` |
