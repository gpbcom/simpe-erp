# 13 — Kubernetes

Everything that runs the application is under `infra/`. This chapter is about
the cluster; [09](09-running-and-deploying.md) covers compose, and the two are
deliberately one description of the system written twice.

## What scales on what

| Workload | Scaled by | Why not the other thing |
|---|---|---|
| **api** | CPU, `autoscaling/v2` | Its work is requests, and requests cost CPU |
| **worker-planning** | KEDA, `planning-runs.*` depth | A consumer waiting on a broker burns almost no CPU. A CPU autoscaler would sit at the floor with a thousand messages queued |
| **worker-notifications** | KEDA, `quote-notifications.*` depth | The same, and it matters more: this queue is what a badge waits behind |
| **frontend** | fixed | It serves static files. There is nothing to autoscale on that the ingress does not already absorb |

### One ScaledObject for every agency

The queues are per-agency — `planning-runs.<company>` — which is what stops one
agency's backlog or poison message delaying everybody else's. Naively that means
one `ScaledObject` per agency, created and destroyed as agencies come and go, by
something that would have to watch the database to know.

The RabbitMQ scaler's `useRegex` avoids all of it:

```yaml
queueName: "^planning-runs\\.(?!.*\\.dlx$).*"
useRegex: "true"
operation: sum
```

The pattern **excludes the dead-letter queues**. Messages there have been given
up on; scaling up to consume them would spin workers against work nothing will
accept.

### `sum` for planning, `max` for notifications

`sum` maximises throughput: every queued run counts toward the replica target,
and a run is a run whoever asked for it.

`max` is the right answer for notifications, and the difference is the point of
the per-agency queues. Under `sum`, one agency submitting a thousand quotes
decides the replica count for *everybody* — which is precisely the coupling the
topology exists to prevent. Under `max` the target is the deepest single queue,
so a busy agency gets capacity without one quiet agency's badge waiting behind
it.

## What the chart refuses to render

`infra/chart/templates/common/guards.yaml`. Each of these is silent at runtime:
the pods start, report Ready, and do the wrong thing.

| Refused | The failure it prevents |
|---|---|
| `solverWorkers` ≠ the planning worker's CPU limit | The solve budget is **wall-clock**. More threads than cores means the kernel throttles the whole cgroup, so thirty seconds takes a minute — and the run still reports as having used its budget. The only symptom is a queue that will not drain |
| CPU request ≠ CPU limit on the planning worker | Anything but Guaranteed QoS is that same throttling, reached from the other side |
| Grace period under 60s on the planning worker | Kubernetes' default is 30, which is *exactly* the solve budget. A scale-down `SIGKILL`s mid-solve and the message is redelivered from the start |
| `workerNotifications.scaling.minReplicas: 0` | A badge should be instant, and a cold start is not |
| `global.image.tag` unset | A moving tag makes a rollback mean "whatever that tag points at now" |

## Draining without losing a solve

Three things have to agree, and they are in three different files:

1. `terminationGracePeriodSeconds: 90` — longer than the solve budget.
2. `WorkerRunner._wait_for_a_signal` handles `SIGTERM` and lets the in-flight
   solve finish and acknowledge rather than being killed mid-message.
3. KEDA's `scaleDown.stabilizationWindowSeconds: 300` — so a queue that has just
   drained does not evict a pod twenty-five seconds into a thirty-second solve.

A `PodDisruptionBudget` per role covers node drains, so one does not take every
consumer at once and leave the queue with nobody on it.

## The API and its streams

The SSE design is already horizontally scalable and needed no change: each API
instance binds its **own** exclusive queue for `notification.created`, so every
instance wakes the readers it happens to hold. No sticky sessions, no shared
state.

What the cluster has to add is at the edge. The ingress carries
`proxy-buffering: "off"` and a long read timeout, because buffering holds every
frame until the connection closes — turning a live feed into one long silence.
The front-end's own nginx already does this internally; without it on the
ingress the setting only applies to the hop nobody was worried about.

Scale-down is otherwise survivable by design: the stream announces `ready` on
every reconnect and the client refetches. A 60-second grace period and a
`preStop: sleep 10` keep that from happening to every reader on every deploy.

## The connection tier

`pool_size: 10` + `max_overflow: 5` is up to **15 PostgreSQL connections per
pod**. At ten API pods and twenty workers that is 450 backends; the default
`max_connections` is 100.

**PgBouncer in `transaction` mode**, and the pool sizes dropped to 3 + 2 per
pod. One trap comes with it, and it is silent: `asyncpg` uses server-side
prepared statements and caches them per connection, so under transaction pooling
a statement prepared on one backend and executed on another raises —
intermittently, under load, naming a statement nobody wrote.
`DatabaseConnectionManager` passes `statement_cache_size=0` unconditionally, and
compose ships a `--profile pooled` so the path is exercised rather than only
documented.

## The ceiling that was not built for

Every worker replica declares **every** agency's queue. At a few hundred
agencies:

- ~300 agencies × 2 roles ≈ **600 quorum queues**, each a Raft cluster
- × 20 replicas ≈ **12,000 AMQP consumers**

Two things were done about it and one was not.

**Done:** the queues are quorum, so a node loss does not take the runs nobody
had picked up yet. **Done:** the dead-letter queues were consolidated from one
per agency to one per role — a few hundred extra Raft clusters holding failures
that arrive at a rate of nearly none.

**Not done:** sharding agencies across replicas. It fights KEDA's variable
replica count, and the number at which it becomes necessary has not been
measured. Measuring it — seed 300 agencies, watch RabbitMQ's memory and consumer
count — is the next piece of work here, and the measurement is the deliverable
rather than a pass or a fail.

## Provider-agnostic, and what that cost

`cluster-autoscaler` rather than Karpenter, because Karpenter is AWS and Azure
and this has to run on Kapsule, a hyperscaler or on-prem alike. Upstream
primitives plus CNCF add-ons throughout; nothing in `infra/` names a cloud.

The stores are operator-managed in-cluster — CloudNativePG, the RabbitMQ Cluster
Operator, the MinIO Operator — rather than managed services, for the same
reason. `s3.endpointUrl` is the one seam where a managed service drops in
without anything else changing.

## Argo CD

| Environment | Sync | Why |
|---|---|---|
| dev | automated, prune, self-heal | A manual change here is somebody experimenting, and reverting it is the right help |
| staging | automated, prune | A manual change here is usually somebody mid-incident |
| **prod** | **none** | The migration hook is irreversible. A sync that ran on its own could migrate a schema nobody was watching |

Image tags are absent from the values files. CI passes
`--set global.image.tag=<git sha>`, so a rollback is a sync to a previous
revision rather than a commit that has to be reverted first.

## The add-ons the chart does not own

cert-manager, ingress-nginx, External Secrets, KEDA, cluster-autoscaler,
kube-prometheus-stack, Loki, Tempo, Alloy, CloudNativePG, PgBouncer, the
RabbitMQ and MinIO operators — all installed by `infra/bootstrap`.

They outlive any one release, and several hold state a reinstall would
invalidate for every other tenant of the cluster. A chart that owned them would
uninstall cert-manager on a failed rollback and take every certificate with it.

**One of them has a deadline.** RabbitMQ must be clustered before the first
deploy: the queues are declared `quorum`, and redeclaring an existing classic
queue with a different type is a `PRECONDITION_FAILED` rather than an upgrade.
→ [05](05-events-and-notifications.md)

## Verifying it

```sh
k3d cluster create rt-erp --agents 3      # proves provider-agnosticism as a side effect
helm install rt-erp infra/chart -f infra/chart/values-dev.yaml \
  --set global.image.tag=$(git rev-parse --short HEAD)
kubectl get job -l helm.sh/hook           # migrations ran once, before the API
robot -d qa/out qa/robot/suites           # the same campaign, against the ingress
```

The claims worth testing rather than asserting:

1. **Independent scaling** — publish 50 planning runs; the planning deployment
   scales and the notification one does not.
2. **Solves survive eviction** — `kubectl delete pod` mid-solve, then
   `kubectl drain` a node. The run completes elsewhere and the message is
   acknowledged exactly once.
3. **No cross-agency clobbering** — two agencies solving overlapping periods
   concurrently, both plans intact afterwards.
4. **No duplicate runs** — redeliver one message to two replicas; exactly one
   `running` transition.
5. **Connection budget** — scale to the maximum and assert PostgreSQL's
   `numbackends` stays under `max_connections`.
6. **The queue-count ceiling** — 300 agencies, and write the number down.
