# 06 — Planning computation

Turning accepted quotes into a week of visits: who goes where, in what order.

## The pipeline

```
accepted quotes over a period
        │  RequirementBuilder
        ▼
InterventionRequirement          one per quote line: service, customer,
        │                        day, window, duration, coordinate
        │  TravelResolver        one per assistant, at their own speed
        ▼
CP-SAT solve  (OR-Tools, 30s budget, on a worker)
        │
        ├── feasible and complete ──▶ Intervention rows replace the period's plan
        └── anything unplaced ──────▶ the run FAILS, with a reason per visit
```

## A partial plan is refused, not stored

This is the decision the whole computation is built around.

A calendar missing three visits still looks like a calendar. Nobody reads the
run record to check, and the visits quietly dropped are exactly the ones that
end with somebody waiting at their door.

So a run that cannot place everything **fails**. The store is never reached,
this week's existing plan stays untouched, and the agency keeps a working
calendar while the problem is fixed.

## And it says why

The solver can only report *that* something did not fit. `explain_unplaced`
works out **why**, testing reasons in order of how actionable they are:

| Order | Reason | Detail given |
|---|---|---|
| 1 | `outside-working-day` | The window falls outside 09:00–20:00 |
| 2 | `out-of-radius` | "the nearest assistant lives 34.2 km away, beyond the 30.0 km radius" |
| 3 | `no-assistant-available` | "all 4 assistants within the radius are absent on 2026-08-12" |
| 4 | `customer-conflict` | It cannot fit alongside another visit to the same customer |
| 5 | `no-feasible-slot` | Travel, lunch and the day's other visits leave no room |

The first that applies is reported and the rest are not tested. A visit nobody
can reach is *also* a visit with no feasible slot, but only the first reading
tells anybody what to change: a manager told "no assistant lives within 30 km of
Mme Durand" can widen the radius or hire. A manager told "INFEASIBLE" can do
nothing.

The reasons are folded into the exception message, so the failed run record is
enough to act on without re-running anything.

**This runs after a failed solve, never before one.** It is a diagnosis, not a
pre-flight gate: the tests are necessary conditions, and something that passes
all of them can still be unplaceable for reasons only the search can find.

## Constraints

| Constraint | Source |
|---|---|
| One assistant at a time | model |
| Inside the requirement's window | the quote line |
| Inside the working day | `planning.day_start_minute` / `day_end_minute` |
| Travel between consecutive visits | `TravelResolver`, per assistant |
| A lunch break | `PlanningSettings.lunch_break_minutes`, in a configured window |
| Within a radius of the assistant's home | `PlanningSettings.max_intervention_radius_km` |
| Not during a declared absence | `AvailabilitySlot` |

The objective minimises travel, with `unassigned_penalty: 100000` — chosen to
dominate any realistic travel cost, so leaving a requirement unplaced is a last
resort rather than a cheap way to avoid a drive.

## Travel

**One resolver per assistant, not one shared.** An assistant with a driving
licence covers ground far faster than one on public transport (30 km/h against
12 km/h), and a single resolver would have to assume the same speed for
everybody — either sending the walker on impossible rounds or wasting the
driver's day.

Distance is straight-line between coordinates, converted by the assistant's
speed. An assistant whose home address never resolved is logged at WARNING and
given no work: silently skipping them would leave them idle all week with
nothing anywhere saying why.

## The rules a manager owns

`PlanningSettings` is a single row holding the radius and the lunch break, edited
through `PUT /api/v1/planning/settings`.

The values in `app.yaml` are a **seed, not a fallback**. Once the row exists,
editing the file changes nothing. Treating the file as a live fallback would let
a redeployment silently overwrite a manager's decision.

Changing them does not re-plan anything; they apply to the next run. Silently
recomputing this week because somebody adjusted a radius would move assistants
who have already been told where to go.

## Storing the result

`replace_for_period` deletes and re-inserts inside **one transaction**, scoped to
the period rather than the run — so re-planning one week does not disturb the
week after it, which a different run produced. A caller refreshing mid-replan
sees the old plan or the new one, never a blank week.

An assignment whose customer has no loadable address is dropped and reported at
ERROR rather than aborting the store: one unreachable customer must not cost the
whole workforce its week.

## Running it

`POST /api/v1/planning/runs` (administrator) records a `PENDING` run, publishes
`planning.run.requested`, and answers **202** with the identifier to poll.

The solve happens on the **worker**. It used to be a FastAPI `BackgroundTask`,
which lost the run on any restart and occupied a web worker for the full thirty
seconds. The message is acknowledged only when the handler returns, so a worker
killed mid-solve leaves the work for the next one.

`execute_run` never raises for a solver problem — the failure is recorded on the
run, because a caller polling for a result needs to be told what went wrong, and
an exception disappearing into a background task would leave the run pending
forever.

## Tests

`tests/service/test_planning_solver.py` and `test_planning_constraints.py` drive
real solves over built scenarios and assert the placements and the diagnoses.
`test_requirement_builder.py` covers the translation from quote lines.


## Asking for one

`POST /api/v1/planning/runs?period_start=&period_end=` — **administrator-only**,
like listing and reading runs. It answers **202** with a `pending` run to poll:
the solve is CPU-bound, runs on a worker with a 30-second budget, and reaches
the worker over the broker.

Nothing in the application ever called it. The endpoints existed, the worker
consumed them, and there was no control anywhere — so a freshly seeded stack had
no planning, no way to ask for one, and nothing on any screen to say why. The
team-planning screen now has the button, gated on the administrator role so a
manager is not offered something that would only answer 403.

The screen polls while a run is in flight and stops when it finishes. When a run
succeeds it invalidates the *visits* as well as the run: they are written by the
worker, behind the screen's back, so nothing else would refresh them — and being
told "75 visits planned" above an empty list is worse than being told nothing.

## A run fails as a whole

One unplaceable visit means **no planning at all**, not a partial one. That is
deliberate — a half-placed week is not a schedule anybody can work from — but it
makes the seeded data's shape load-bearing.

It was wrong. The seeder's first service window opened at **08:00** while
`planning.day_start_minute` puts the day at **09:00**, so sixteen of
seventy-seven seeded visits were outside the working day and every run failed
with `outside-working-day`. A fixture that cannot be satisfied by construction
looks exactly like a broken solver.

`tests/seed/test_seeded_windows.py` now asserts every seeded window against the
configuration's own bounds — not against 09:00 and 20:00 written down a second
time, because two copies of a number drift and that drift is what caused this.
