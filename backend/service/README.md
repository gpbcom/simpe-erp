# service

Business logic. Depends on `models` and `storage`, and knows nothing about HTTP.

```
auth/  companies/  customers/  emails/  hcas/  intervention_types/
messaging/  notifications/  planning/  quotes/  utils/
```

**One service per entity.** `PlanningService` absorbed the settings service and
the feasibility checker for that reason.

**A service raises its own `MT*` exception**, never `HTTPException`. It travels
untouched to `api/exception_handlers.py` and is translated once — that is the
whole reason the class exists, because the same failure used to be caught,
logged and translated once per endpoint.

**Row-level ownership lives here**, not in the routes. A guard proves the caller
is *an* assistant; only a comparison against the stored record stops assistant A
acting on assistant B's.

Notable pieces:

- `planning/plannings.py` — the CP-SAT solve, the travel resolvers, and the
  diagnosis of what could not be placed. → [docs/06](../../docs/06-planning-computation.md)
- `quotes/quotes.py` — pricing, VAT, surcharges and the validation state machine.
  → [docs/04](../../docs/04-quote-lifecycle.md)
- `messaging/` — the broker publisher and consumer. A failed publish **never
  raises**. → [docs/05](../../docs/05-events-and-notifications.md)
- `emails/` — stdlib SMTP on a worker thread, with `.xlsx` attachments.
