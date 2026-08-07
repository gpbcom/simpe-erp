# infra

Everything that runs SimpleERP rather than everything SimpleERP is. The
application lives in [`backend/`](../backend) and [`frontend/`](../frontend);
this directory holds the descriptions of how to stand it up.

```
infra/
  compose/     the local and single-host stacks
  chart/       the Helm chart
  argocd/      one Application per environment
  bootstrap/   cluster add-ons the chart deliberately does not own
  observability/
               collector config and dashboards — shared by compose and the
               cluster, so a dashboard that works on a laptop works in
               production
  chart/rules/
               the alert rules, canonically. They live under the chart
               because Helm cannot read a file outside its own directory;
               the compose overlay mounts them from there.
```

## Running it locally

```sh
cd infra/compose
cp .env.example .env
docker compose up --build
```

`.env` **must sit beside the compose files**, not at the repository root.
Compose reads it from the project directory, which is the directory of the
first `-f` file. A `.env` left at the root is silently not read, and the stack
comes up on the development defaults without saying so. `COMPOSE_FILE` in
`.env.example` is what makes the bare `docker compose up` above pick up the
development overlay.

From the repository root, or in CI, name both files explicitly:

```sh
docker compose -f infra/compose/docker-compose.yaml \
               -f infra/compose/docker-compose.dev.yaml up -d --build
```

## The one thing that will bite

The base compose file declares `name: rt-erp`. **Do not remove it.** Compose
otherwise names the project after the directory holding the first compose file,
which since the move is `compose` — and the volumes with it. PostgreSQL, MinIO
and RabbitMQ bake their credentials in when they first initialise an *empty*
volume, so switching to a fresh set does not present as an empty database. It
presents as:

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "simple_erp"
```

which reads exactly like a typo in the configuration while the real answer is
that the data is still there, under `rt-erp_postgres-data`, and nothing is
looking at it. `docker volume ls | grep rt-erp_` is the check.

## The observability stack

Five more containers and about a gigabyte of memory, and **part of the
development stack** rather than an overlay somebody has to remember.
Instrumentation nobody runs is instrumentation nobody has looked at, so `up` is
no longer the cheap thing and in exchange a dashboard cannot rot unnoticed.

```sh
cd infra/compose
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up
```

| | |
|---|---|
| Grafana | <http://localhost:3000> — no sign-in, three datasources provisioned |
| Prometheus | <http://localhost:9090> — including the alert rules |
| Planning worker metrics | <http://localhost:9101/metrics> |
| Notification worker metrics | <http://localhost:9102/metrics> |

**It exists so the instrumentation is something somebody has looked at.** The
sibling mega-trends repository has Prometheus, Loki and Promtail blocks in its
compose file, all commented out and none of them ever run — so its dashboards
were written against an idea of the metrics rather than the metrics themselves.

Everything under `observability/` is read by both this overlay and the chart:
the same alert rules, the same collector pipeline. An alert that fires on a
laptop and not in production, or the reverse, teaches people that the ones they
see locally do not mean anything.

## Running through a connection pooler

```sh
docker compose --profile pooled up
```

Then point `database.host` at `pgbouncer`. Nothing else changes, and that is the
property being demonstrated — `asyncpg` uses server-side prepared statements and
caches them per connection, which under transaction pooling breaks
intermittently, under load, naming a statement nobody wrote. The engine passes
`statement_cache_size=0` unconditionally to prevent it, and this profile is what
keeps that setting honest.

## Why compose and Kubernetes both live here

They are two descriptions of one system, and the rule is that they change
together. Each of these is one arrangement written twice:

| | compose | chart |
|---|---|---|
| Migrations | one-shot `migrate` service, `service_completed_successfully` | `pre-install,pre-upgrade` hook Job |
| Workers | `worker-planning`, `worker-notifications` | two Deployments, two KEDA `ScaledObject`s |
| Solver threads | `deploy.resources.limits.cpus` | CPU limit, Guaranteed QoS |
| Draining a solve | `stop_grace_period: 90s` | `terminationGracePeriodSeconds: 90` |
| Observability | part of `docker-compose.dev.yaml` | `bootstrap/` add-ons |
| Alert rules | mounted from `chart/rules/` | the same files, as a `PrometheusRule` |
| Trace pipeline | `observability/otel/collector.yaml` | the same file, as a ConfigMap |
| Connection pooling | `--profile pooled` | PgBouncer in front of CloudNativePG |

A change made to one and not the other is the bug this table exists to catch.

## What is deliberately not here

Cluster add-ons — cert-manager, ingress-nginx, External Secrets, KEDA,
cluster-autoscaler, the metrics and tracing stack — are installed by
`bootstrap/`, not by the chart. They outlive any one release of the
application, and a chart that owned them would uninstall them on a failed
rollback.
