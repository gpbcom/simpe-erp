# 14 — Observability

Three stores, one instrumentation API, and a rule that everything here is shared
between a laptop and the cluster.

| | Answers |
|---|---|
| **Prometheus** | Is it up, how deep is the queue, how long did that take |
| **Loki** | What did it log, and about which agency |
| **Tempo** | Where did *this* planning run spend forty seconds |

**All of it runs in the development stack**, from the ordinary
`docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up` — there
is no overlay to remember. That is the point: instrumentation nobody has
looked at is instrumentation written against an idea of the metrics rather
than the metrics, and the sibling repository has Prometheus, Loki and Promtail
blocks in its compose file, all commented out, and its dashboards show it.

It costs five containers and roughly a gigabyte, which is the trade. Two
things follow from it, and both are visible in `app.dev.yaml`:
`tracing_enabled` is **true**, because a collector is now guaranteed to be
there to receive the spans; and the three application services run
`conf/logger.k8s.yaml`, because Alloy parses their stdout with a
`stage.json` and a coloured console line is one Loki cannot label. Set
`SIMPLE_ERP_LOGGER=conf/logger.yaml` to get the colour back and give up the
Loki fields.

## Logs

`conf/logger.k8s.yaml`, selected by `SIMPLE_ERP_LOGGER`. **JSON to stdout and
nothing to disk**: a rotating file inside a container is invisible from outside
it, unbounded on a layer nobody sized for it, and gone when the pod is replaced.

`JsonLogFormatter` does two things worth knowing:

**One line per record, always.** A pipeline splits on newlines, so a formatter
that let one through would turn a single traceback into eight entries — seven
unparseable, and the one carrying the message not the one carrying the stack.
The exception is a *field*.

**Anything a caller attached with `extra=` becomes a field.** `company_id`,
`routing_key`, `run_id` — queryable, rather than something to grep a sentence
for, where the grep is wrong the first time somebody rewords the message. What
separates those from the logging machinery's own attributes is an explicit
reserved set, taken from `LogRecord`'s documented attributes rather than guessed.

Alloy promotes `trace_id` and `level` to Loki labels. **`company_id` stays a
field**: a label whose values grow with the number of agencies is a stream per
agency, and Loki charges for cardinality the way Prometheus does.

## Metrics

`ApplicationMetrics` holds **its own registry**, not the global default. The
default is process-wide and implicitly shared, so a second instance raises a
duplicate-timeseries error — in a test suite, at a distance, naming neither test.

**Only figures nothing else already has.** Request rates come from the ingress,
queue depths from the RabbitMQ exporter, CPU and memory from the kubelet. What
is here is what only this application knows.

| Metric | Answers |
|---|---|
| `planning_run_duration_seconds{outcome}` | Is the thirty-second budget the binding constraint |
| `planning_run_unplaced_total{reason}` | Why visits are being dropped |
| `planning_run_scheduled_visits` | Whether a fast run actually placed anything |
| `worker_messages_total{role,routing_key,outcome}` | Throughput, and the dead-letter rate |
| `worker_message_duration_seconds{role,routing_key}` | Which role is slow, and on which topic |
| `notification_stream_clients` | Whether the ingress is silently dropping SSE |

### Two decisions inside those

**`planning_run_unplaced_total` is pre-seeded to zero for every
`UnplacedReason`.** A counter that has never fired is *absent*, not zero, and an
absent series makes `rate()` return nothing rather than zero — so the alert on
"visits are being dropped for want of a qualification" would stay silent on
exactly the deployment where it has never yet happened, which is the one it
exists for.

**No label identifies a person.** No `hca_id`, no `customer_id`, no
`company_id`. A label whose values grow with the workforce is a new time series
per person, and the usual way a metrics store is taken down by the application
it is watching. There is a test asserting it on the declared label *names*
rather than on the rendered text — `no-assistant-available` is a *reason*, and a
text search would read it as a per-assistant label and fail for the wrong
reason.

### Four message outcomes, not two

`handled`, `failed`, `unhandled`, `unreadable`. They need different answers:
`failed` is a handler that raised and a message that dead-lettered; `unreadable`
usually means a deployment in progress; **`unhandled` is a topic bound to a
queue nothing answers**, which is a topology mistake and is completely silent
without this — the message is acknowledged and the work simply does not happen.

### Where they are served

`/metrics` on the API's own port, and on the worker's `9100` — a port it did not
have. Without one it also had no readiness probe, so Kubernetes reported a
worker Ready the instant its process started, before it had a database, a broker
connection or a single queue bound.

Both are **unauthenticated**, because a scraper has no account to sign in with.
What makes that defensible is the paragraph above: the body carries counts and
durations and labels drawn from enums. `/metrics` is also absent from the
OpenAPI document — it is not part of the API a client programs against, and
including it would put a non-JSON endpoint in a schema every generator reads.
The ingress does not route it.

## Traces

OTLP to a collector, and the application knows no other tracing address.

**The one piece that is not automatic is the broker.** Every instrumentation
library propagates trace context over HTTP and none of them does it over a
broker, so without carrying it a trace stops at `POST /api/v1/planning/runs` and
the thirty seconds that actually matter are attributed to nothing.
`EventEnvelope.traceparent` carries it; `TraceContext` reads and restores it.

It is nullable, because a queue is not drained the instant a deployment lands. A
malformed one is **refused** rather than dropped — extracted leniently it starts
a *new* trace, and a solve that appears to have begun on its own reads as a
complete picture while being the wrong one.

`TraceContext` imports OpenTelemetry optionally, once, at module level. Without
the package every method returns `None`, which is exactly what a deployment with
tracing off does anyway. Installing it is what makes tracing live, with no call
site changing.

**Sampling belongs to the collector**, not to the application. The collector
sees every service's traffic and can decide consistently; a rate set per process
produces traces complete for one hop and missing the next, which looks like the
missing service never ran. The policies keep everything that errored, everything
slow, and 10% of the rest — a thirty-second planning run sampled away is the
only span anybody wanted.

## Alerts

`infra/chart/rules/simple-erp.yaml`, read by the chart as a `PrometheusRule` and
mounted by the compose overlay. **One file**, because an alert that fires on a
laptop and not in production teaches people that the local ones do not mean
anything.

Nothing here is about CPU, memory or restarts. The kubelet already reports those,
and an alert that duplicates one is a second page for one incident. Every rule is
about work not happening.

| Alert | The thing that would otherwise be silent |
|---|---|
| `VisitsUnplaceableForWantOfAQualification` | A requirement nobody holds fails every run it touches, and the message reads as a staffing problem rather than a catalogue mistake |
| `MessagesArriveOnATopicNothingHandles` | Acknowledged and discarded. The work is lost with no failure recorded anywhere |
| `PlanningRunsAreStuckPending` | `EventPublisher` never raises by design, so a run recorded but never queued leaves one ERROR line and nothing else |
| `MessagesAreBeingDeadLettered` | The rate is nearly always zero, which is what makes "more than none" the right threshold |
| `PlanningRunsExceedTheirBudget` | Points straight at `solver_workers` against the CPU limit |
| `PlanningQueueIsNotDraining` | Either the workers are not scaling or they are not ready — check `/ready` before adding replicas |
| `NoServerSentEventReadersAtAll` | Expected overnight; during the day it means the ingress is closing the stream path |

## Where LangChain will fit

There is no LLM code in this repository today. The decision that matters was
made anyway, because it is the one that is expensive to reverse:

**The application speaks OTLP and nothing else.** When LLM observability
arrives, the temptation is a second stack beside this one — a Langfuse SDK
alongside an OTel SDK, two sets of credentials, two trace ids for one request.
Instead the exporter is added to `infra/observability/otel/collector.yaml` and
the application does not change: LLM spans routed to Langfuse on their
`gen_ai.system` attribute, everything else to Tempo, **one trace id throughout**.
A request that called a model is one trace, not two.

The commented exporter is in that file already, so the shape of the decision is
on the record rather than in somebody's memory.

Two more things follow from the architecture as it stands:

**A LangGraph run belongs behind the broker**, as a third `WorkerRole` with its
own queue and its own `ScaledObject`. It is the mirror image of the planning
worker — LLM calls are I/O-bound and long, so its pods want many replicas per
core where planning wants few and whole ones. The two cannot share a deployment,
an HPA or a node pool, which is the second and larger reason the worker split
pays for itself. The `traceparent` work above is what will make such a run trace
back to the request that asked for it.

**Not inside the request path.** This codebase already learned that once:
`BackgroundTasks` was removed for the planning solve because it lost the run on
any restart and occupied a web worker for thirty seconds. An LLM call is the same
shape. → [01](01-architecture.md)
