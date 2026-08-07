# bootstrap

The cluster add-ons the chart deliberately does **not** own.

They outlive any one release of the application. A chart that owned them would
uninstall cert-manager on a failed rollback, and take every other workload's
certificates with it.

Install order matters only where it is noted.

| | Why it is here |
|---|---|
| **cert-manager** | Issues the ingress certificate. Must exist before the chart, or the Ingress references a ClusterIssuer that is not there |
| **ingress-nginx** | The ingress class the chart names. Its `proxy-buffering: off` annotation is what keeps the notification stream a stream |
| **External Secrets Operator** | Writes the one Secret every workload reads. The chart declares an `ExternalSecret`; this is what acts on it |
| **KEDA** | The workers' autoscaler. Without it the `ScaledObject`s are inert and both workers sit at their replica floor |
| **cluster-autoscaler** | Adds nodes. Chosen over Karpenter deliberately: Karpenter is AWS and Azure, and this has to run on Kapsule, a hyperscaler or on-prem alike |
| **kube-prometheus-stack** | Reads the `ServiceMonitor`, `PodMonitor` and `PrometheusRule` the chart ships |
| **Loki + Grafana Alloy** | The logs. Alloy reads the kubelet's stream, which is why the application writes JSON to stdout and nothing to disk |
| **Tempo + OpenTelemetry Collector** | The traces. The collector is the only tracing address the application knows; the fan-out happens inside it |
| **CloudNativePG** | PostgreSQL, with backups and failover |
| **PgBouncer** | In front of it. Every replica opens up to `pool_size + max_overflow` connections, and at the chart's replica counts that is more backends than PostgreSQL's default `max_connections` |
| **RabbitMQ Cluster Operator** | The broker. **Cluster it before the first deploy** — the queues are declared `quorum`, and changing an existing classic queue's type is a `PRECONDITION_FAILED` rather than an upgrade |
| **MinIO Operator** | Object storage, or point `s3.endpointUrl` at a managed one |

## The one that has a deadline

The RabbitMQ note above is the only item here with an ordering constraint that
cannot be fixed later without downtime. `EventConsumer` declares its queues with
`x-queue-type: quorum`; redeclaring an existing classic queue with a different
type fails, so a deployment that ran on classic queues first needs them drained
and deleted before this version will consume at all.

Do it while there is at most one deployment to drain.

## Why none of this is a chart dependency

A Helm dependency is installed and uninstalled with its parent. These are
cluster-scoped, shared, and slower-moving than the application — and several of
them (cert-manager, ESO) hold state that a reinstall would invalidate for every
other tenant of the cluster.
