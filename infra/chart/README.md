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

- `workerPlanning.solverWorkers` not equal to its CPU limit. The solver's budget
  is wall-clock, so more threads than cores means the kernel throttles the whole
  cgroup and thirty seconds of budget takes a minute of real time. The run still
  reports as having used its budget, so the only symptom is a queue that will
  not drain.
- The planning worker's CPU request not equal to its limit. Anything but
  Guaranteed QoS is the same throttling, reached from the other side.
- A termination grace period under 60s on the planning worker. Kubernetes'
  default is 30, which is *exactly* the solve budget — so a scale-down SIGKILLs
  mid-solve and the message is redelivered from the start.
- `workerNotifications` scaling to zero. A badge should be instant; a cold start
  is not.

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
