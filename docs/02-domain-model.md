# 02 — Domain model

Every model is a Pydantic class in `backend/models/src/models/`, with per-field
validators that raise its own `MT*` exception family. Validation runs on the way
**in and out** of the database, so a value that stopped being valid is caught at
the boundary rather than propagating.

## The shape of the business

```
Company ──┬── Hca ──────── AvailabilitySlot
          │     └───────── Certification, DrivingLicense
          └── User (account)

Customer ──── Quote ──── QuoteLine ──── InterventionType
                 └────── QuoteTypeWeekAggregate

PlanningRun ──── Intervention  (one per placed QuoteLine)

Notification ──▶ User
```

## People

**`Hca`** — a home care assistant. Identity, address, contract, qualifications,
an optional driving licence, an optional photograph, and declared absences.
`can_drive()` decides which travel speed the planner uses for them;
`is_available_on(day)` is what an absence removes them from.

**`Customer`** — somebody served. Identity, address, and a
`RegistrationStatus`. A stopped customer gets no new interventions.

**`User`** — an account. Carries `role`, an optional `hca_id` binding it to an
assistant record, `company_id`, and `must_change_password`. `owns_hca(id)` is
the row-level check the planning and self-service routes rest on.

**`HcaApplication`** — somebody asking to be hired, before they are an `Hca`.

## Quoting

**`Quote`** — a priced offer to one customer. Header, lines, per-week aggregates,
and four authorship fields: `authored_by`, `submitted_at`, `validated_by`,
`validated_at`.

The aggregates are **derived from the lines but stored alongside them**.
Recomputing on read would be cheap; the reason to store them is that a reprinted
quote must show the figures it showed when it was issued, even after a service
is renamed or repriced.

**`QuoteLine`** — one service on one day, in a window (`earliest_start` …
`latest_end`) that must be at least as long as its `duration_minutes`. Prices
are `Decimal`, never float, and reach the wire as **strings** — JSON numbers are
binary floats, and money is not.

**`InterventionType`** — a catalog entry: a name, a code, a category that
decides the VAT rate, and a base hourly rate. Retired with `is_active` rather
than deleted, because a quote issued last year still references it.

## Planning

**`PlanningRun`** — one execution of the computation. Its
`unassigned_requirement_ids` is the honest part of the result.

**`Intervention`** — one scheduled visit. The assistant's name and the
customer's address are **copies taken when the visit was planned**, not joins. A
planning is a document an assistant works from; re-resolving it against live
records would make a printed round disagree with the screen after any edit.

Neither the model nor the table carries `created_at`. A visit is not
independently dated — it exists because a run produced it, is deleted with that
run, and the run's `started_at` is when it came into being.

**`HcaPlanning`** — one assistant's diary over a period.

## Notifications

**`Notification`** — something that happened, addressed to **one** account.

One row per recipient, not one per event: a quote submitted to an agency with
three managers writes three rows. Read state belongs to a person, and two
managers must be able to disagree about whether they have dealt with something.

The text is **stored, not templated at read time**. What a manager was told is
what they were told; regenerating it would rewrite history after a customer is
renamed.

## Geography

**`PostalAddress`** — flattened onto columns rather than stored as a blob,
because the planner filters on the city and reads the coordinates on every
solve. It **geocodes against Nominatim during validation**, and treats an
address that already carries a coordinate or a `geocoding_error` as resolved —
which is what lets a page of stored rows be rebuilt without a single network
request.

## Every enum

From `backend/models/src/models/enums.py`.

| Enum | Values |
|---|---|
| `UserRole` | `hca` < `manager` < `admin`, with `has_at_least()` |
| `AccountOrigin` | `self-registered`, `created-by-staff` |
| `RegistrationStatus` | `active`, `stopped` |
| `ContractType` | `cdi`, `cdd`, `interim`, `internship` |
| `ServiceCategory` | `necessity` (VAT 5.5 %), `comfort` (VAT 20 %) |
| `QuoteStatus` | `draft`, `pending-validation`, `sent`, `accepted`, `rejected`, `expired` |
| `InterventionStatus` | `planned`, `confirmed`, `completed`, `cancelled` |
| `AvailabilityKind` | `holiday`, `day-off`, `sick-leave`, `training`, `unavailable` |
| `PlanningRunStatus` | `pending`, `running`, `succeeded`, `failed` |
| `UnplacedReason` | `out-of-radius`, `no-assistant-available`, `outside-working-day`, `customer-conflict`, `no-feasible-slot` |
| `HcaApplicationStatus` | `pending`, `approved`, `rejected` |
| `NotificationKind` | `quote-submitted`, `quote-validated`, `quote-refused`, `planning-completed` |
| `EventRoutingKey` | `quote.submitted`, `quote.validated`, `quote.refused`, `planning.run.requested`, `planning.run.completed` |
| `Weekday` | `monday` … `sunday` |
| `ProbeStatus`, `DatabaseStatus` | health-probe values |

`QuoteStatus.EXPIRED` is declared and **nothing ever sets it** — there is no
expiry job, and `valid_until` is stored but not acted upon. Worth knowing before
you build a screen around it.

## Migrations

| # | Adds |
|---|---|
| 0001 | People and accounts |
| 0002 | Intervention types |
| 0003 | Quotes, lines, aggregates |
| 0004 | Planning runs and interventions |
| 0005 | Companies, applications, planning settings |
| 0006 | Quote validation: `pending-validation`, four authorship columns, and a **widened `status` column** |
| 0007 | Notifications |

The widening in 0006 is the one to remember. `status` was `String(16)`, sized
when `accepted` was the longest value; `pending-validation` is eighteen
characters. SQLite truncates silently and PostgreSQL errors — so without that
migration the feature passes the whole test suite and fails on first contact
with the real database.

`tests/storage/test_migrations.py` walks every revision against a temporary
database and diffs the result against `Base.metadata`, so ORM/migration drift
fails a test rather than a deployment.
