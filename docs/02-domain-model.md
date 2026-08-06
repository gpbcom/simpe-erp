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

**Everybody belongs to exactly one agency.** `company_id` is required on `User`
and on `Hca` alike — administrator, manager and assistant — and `NOT NULL` in
both tables since migration `0008`. It was optional while companies were newer
than the rows pointing at them; nothing keeps that true now. An account without
an agency is covered by no per-company scoping and produces events that cannot
be routed to a queue, so the state is refused rather than stored and puzzled
over later.

Where the agency comes from is never the caller's choice:

| Account created by | Agency taken from |
|---|---|
| Self-registration (`POST /auth/register`) | The assistant record it names |
| A manager (`POST /auth/accounts`) | The assistant record, over the caller's own |
| Founding an agency (`POST /companies/registration`) | The agency created by the same call |

Removing the last exemption mattered on its own: an administrator belonging to
no agency used to be treated as system-wide when deciding applications, which
meant **any** administrator without an agency could decide every agency's
queue.

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


## The VAT category belongs to the quote line

`QuoteLine.service_category` decides the rate a line is taxed at — 5.5% for
necessity care, 20% for comfort care. It used to live on the catalogue entry,
and it was moved because **the same service is necessity care for one customer
and comfort care for another**: help with washing under a care plan is billed at
the reduced rate, and the same hour arranged privately is not. Which it is
depends on who is being quoted, not on what is being sold.

While it lived on the catalogue, an agency serving both had to keep two entries
for one service and remember which was which — and every quote written against
the wrong one was mis-taxed with nothing on screen to show it.

What the catalogue still decides is the **hourly rate**. It no longer decides
the tax.

The field has **no default**. Defaulting to necessity would understate the tax
on every line somebody forgot to set, an error that surfaces at the tax return
rather than on the screen; defaulting to comfort would overcharge families
entitled to the reduced rate. A line without a category is not a line. The two
quote dialogs *suggest* the catalogue entry's own category when a service is
picked, and leave the field editable.

Migration **0009** adds the column, backfills it from each line's catalogue
entry — reproducing exactly the VAT every existing quote was priced at — and
only then makes it `NOT NULL`. No issued quote changes its total: a customer is
never re-billed for work already quoted.
