# The chart

```sh
helm lint infra/chart --set global.image.tag=$(git rev-parse --short HEAD)
helm template simple-erp infra/chart \
  -f infra/chart/values.yaml \
  -f infra/chart/values-dev.yaml \
  --set global.image.tag=$(git rev-parse --short HEAD)
```

**`global.image.tag` is required and has no default.** The chart fails to render
without one rather than falling back to `latest`: a moving tag makes a rollback
mean "whatever that tag points at now", which is not a rollback. That is also
why a bare `helm lint infra/chart` fails — pass the tag.

## What it will refuse to render

`templates/common/guards.yaml` holds checks for the mistakes that are silent at
runtime — the pods start, report Ready, and do the wrong thing:

- `workerPlanning.solverWorkers` not equal to its CPU limit. More threads than
  cores means the kernel throttles the whole cgroup, so the wall-clock net
  arrives after less real search. The run still reports as having used its
  allowance, so the only symptom is a queue that will not drain.
- The planning worker's CPU request not equal to its limit. Anything but
  Guaranteed QoS is the same throttling, reached from the other side.
- `workerPlanning.solverTimeLimitSeconds` below eight times
  `solverDeterministicBudget`. The two measure different things — seconds and
  solver work units — so nothing makes them agree by construction. This chart
  shipped that mistake: it pinned the net at 30.0 and never set the budget at
  all, so a cluster stopped every solve a fifth of the way into the search it
  needed, left visits unplaced that a full search places, and logged on every
  run that the plan was not reproducible.
- A termination grace period under 60s on the planning worker. Kubernetes'
  default is 30 and a real solve is minutes, so a scale-down SIGKILLs mid-solve.
  No work is lost — the message goes unacknowledged and another replica takes
  it — but the whole solve is repeated.
- `workerNotifications` scaling to zero. A badge should be instant; a cold start
  is not.
- An empty `integrations.providers`. The cluster would come up serving every
  screen except the one that makes the agency compliant: a gallery with nothing
  to connect. Electronic invoicing is a legal obligation, not a feature.

## The two bill announcements have to be switched on

`billingWebhook.enabled` governs both of them: approval, which emails the
rendered invoice to its customer, and collection, which transmits it to the
certified platform. Both are the API calling itself over the in-cluster
Service — routing them through the ingress and back would put a public hop, a
TLS handshake and a rate limiter inside the application.

**The chart had no `billing_webhook` block at all**, so a cluster ran the
model's defaults: disabled, at `localhost:8000`. Nothing failed and nothing was
logged as wrong; an approved invoice was simply never emailed, and — once
automatic transmission on payment existed — a collected one was never sent to
the platform. It is rendered now, still off by default, and turning it on is one
value.

## The e-invoicing platforms are values, not code

`integrations.providers` lists the certified platforms an agency may connect
to — display name, documentation link, what each can be asked to transmit, and
which credential fields its dialog must ask for. It is rendered into the
ConfigMap and read by the backend.

**It is values because the French registry moves and this chart should not have
to.** A platform whose registration lapses is a `helm upgrade`; so is a fifth
one publishing an API. Coverage is declared conservatively — a route a
platform's own documentation does not mention is not claimed, which is why
Storecove does not list `chorus-pro` and the backend refuses a public body's
invoice through it rather than sending it into silence.

`EINVOICING_CREDENTIAL_KEY` is the key those credentials are encrypted with, and
it is not like the other secrets in the list. The others are credentials for
something the cluster can be issued again; **this one is the only thing that can
read an agency's stored platform credentials back, so losing it means every
agency must re-enter its platform API key.** The store holding it needs the same
backup discipline as the database.

Only the API pod ever resolves it. A worker publishes `bill.paid` and calls the
loopback webhook; the transmission — and so the one decryption — happens in the
API. The Secret is mounted the same way everywhere because there is one
`envFrom`, but nothing else reads that key.

## The two workers are not variations of each other

| | planning | notifications |
|---|---|---|
| KEDA `operation` | `sum` — maximise throughput | `max` — one agency's backlog must not decide everybody's replica count |
| `minReplicaCount` | 1 | 1, and the guard refuses 0 |
| QoS | Guaranteed | Burstable |
| Grace period | 90s, longer than the solve budget | 30s |
| Node pool | its own, tainted, in production | wherever |

One `ScaledObject` covers every agency, through the RabbitMQ scaler's regex
support. The queues are per-agency, so without it this would be one object per
agency — created and deleted as agencies come and go, by something that would
have to watch the database to know.

## What is deliberately absent

- **Postgres, RabbitMQ, the metrics stack, the ingress controller.** They are
  installed by [`../bootstrap`](../bootstrap/README.md) and outlive any one
  release; a chart that owned them would uninstall them on a failed rollback.
- **`/metrics` from the Ingress.** It is served for a scraper inside the
  cluster. Routing it publishes it.
- **A tag in the values files.** CI passes `--set global.image.tag=<git sha>`,
  so a rollback is a sync to a previous revision rather than a commit.
