# worker

The broker consumer. Depends on `models`, `storage` and `service` — **and
deliberately not on `api`**: a background consumer that pulled in FastAPI and
uvicorn to read one YAML file would make the dependency graph a ring, so it
duplicates fifteen lines of logging setup instead.

```sh
uv run worker
```

Two queues, consumed in one process:

| Queue | Handles |
|---|---|
| `planning-runs` | The CP-SAT solve, then announces the outcome |
| `quote-notifications` | The notification fan-out, and the planning-failure notice |

Two rather than one because a solve pins a core for thirty seconds, and sharing
a queue would leave a manager waiting behind work that has nothing to do with
them.

**A message is acknowledged only when its handler returns.** A worker killed
mid-solve leaves it for the next one. A handler that raises dead-letters the
message rather than requeuing it, because a message that fails once will usually
fail again.

Each handler opens its own session and closes it before returning.
`SIGTERM` is handled so an in-flight solve finishes rather than being redelivered
from the start.

Runs the **same image** as the API with a different entry point.

→ [docs/05](../../docs/05-events-and-notifications.md)
