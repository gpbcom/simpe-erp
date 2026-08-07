# 06 — Planning computation

Turning accepted quotes into a week of visits: who goes where, in what order.

## The pipeline

```
accepted quotes over a period
        │  RequirementBuilder    resolves each line's required certifications
        ▼                        and skills against its catalog entry
InterventionRequirement          one per quote line: service, customer,
        │                        day, window, duration, coordinate,
        │                        required certification and skill codes
        │  TravelResolver        one per assistant, at their own speed
        ▼
   field employees only          `field_employee` filters the workforce first
        ▼
CP-SAT solve  (OR-Tools, 30s budget, on a worker)
        │
        ├── feasible and complete ──▶ Intervention rows replace the period's plan
        └── anything unplaced ──────▶ the run FAILS, with a reason per visit
```

## Who the solver is even allowed to consider

`_field_employees` is the single point where that is decided, and it runs
before anything else. Before it existed the planner took **every** assistant
record there was, so an office-based coordinator with a record — or a manager
who holds one because they also cover rounds — was equally schedulable and
equally not.

**The flag is the only input, and the role is not an input at all.** The run is
handed `Hca` records; `UserRole` does not appear in it. So a manager or an
administrator whose account is bound to a record — the ordinary shape for
somebody promoted from an assistant, since promotion keeps the `hca_id` — is
planned exactly like anybody else the moment their flag says so. Adding a role
check here is the tempting answer to "why is a manager on this round?", and it
would silently withdraw every manager who genuinely covers them.

**It was writable in name only until recently.** `EmploymentUpdateRequest`
carried `field_employee`, both screens sent it, and the endpoint called
`set_employment(hca_id, contract_type, certifications)` — three arguments — so
the value was dropped and the repository's own default put it back to `True`.
A manager switching somebody off got a 200 and no change; worse, an unrelated
contract edit silently put back anybody who *had* been switched off. Neither is
visible until a run schedules somebody nobody expected. The argument is
required at every layer now, so the same omission is a `TypeError` rather than
a wrong row.

The filter is here rather than in the repository on purpose. A manager's
workforce screen must still show everybody; a query that quietly dropped the
office staff would make them look dismissed.

An empty pool is a legitimate answer, logged at `WARNING`: every requirement
comes back unassigned and the run fails, which is correct and traceable. What
must not happen is the filter silently falling back to the whole workforce.

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
| 1 | `outside-working-day` | "its window falls outside the 09:00–20:00 working day" — the hours quoted are the agency's stored ones |
| 2 | `missing-certification` | "none of the 12 field employee(s) holds DEAES unexpired on 2026-08-12" |
| 3 | `missing-skill` | "none of the 12 field employee(s) has declared LEVE-PERSONNE unexpired on 2026-08-12" |
| 4 | `out-of-radius` | "the nearest assistant lives 34.2 km away, beyond the 30.0 km radius" |
| 5 | `not-a-working-day` | "none of the 4 assistant(s) within the radius works a wednesday" |
| 6 | `no-assistant-available` | "all 3 assistant(s) within the radius who work that day are absent on 2026-08-12" |
| 7 | `customer-conflict` | It cannot fit alongside another visit to the same customer |
| 8 | `no-feasible-slot` | Travel, lunch and the day's other visits leave no room |

**`missing-certification` comes before anything geographical**, and that
placement is the point. A visit nobody is qualified for is *also* a visit
nobody within the radius can take, so reporting the distance would send a
manager to widen a radius that was never the problem. "Nobody here holds DEAES"
names a hire, a training course, or a requirement that was wrong.

**`missing-skill` follows it, and the order between the two is not
arbitrary.** A certification is obtained; a skill is merely declared. A visit
blocked by both is reported against the one that takes longer to fix, because
the other reading would send a manager to chase somebody's profile when the
real obstacle was a diploma nobody in the agency holds. The skill test runs on
the candidates the certification test left rather than starting again from the
whole workforce — otherwise a visit whose real obstacle is the diploma would be
reported as a skill gap counting people who were never eligible anyway.

**`not-a-working-day` comes before `no-assistant-available`**, and the two
are genuinely different answers. "Nobody works Sundays" is a rota or a
recruitment decision; "everybody is on leave that week" resolves itself.
Folding them together would report the second when the first is true, and
send a manager through absence records looking for a day nobody had ever
agreed to work.

It also **narrows the workforce for every test after it**. Reporting "all 6
assistants within the radius are absent" when only one of them was qualified
sends a manager to look at the rota when the answer was the rota of one
person.

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
| Inside the working day | `PlanningSettings.day_start_minute` / `day_end_minute` |
| Travel between consecutive visits | `TravelResolver`, per assistant |
| A lunch break | `PlanningSettings.lunch_break_minutes`, inside `lunch_window_start_minute` / `lunch_window_end_minute` |
| Within a radius of the assistant's home | `PlanningSettings.max_intervention_radius_km` |
| On a day the assistant works at all | `Hca.working_weekdays` |
| Not during a declared absence | `AvailabilitySlot` |
| Holding every qualification the work requires | the quote line, or its catalog entry |
| Being a field employee at all | `Hca.field_employee` |

The objective minimises travel, with `unassigned_penalty: 100000` — chosen to
dominate any realistic travel cost, so leaving a requirement unplaced is a last
resort rather than a cheap way to avoid a drive.

### The budget is wall-clock, and that decides the thread count

`solver_time_limit_seconds: 30.0` is real time, not CPU time. `solver_workers`
is how many parallel search threads CP-SAT may run, and it was **hard-coded at
8** against a container capped at two cores.

Under a container CPU *limit* that does not merely fail to help: the kernel
throttles the whole cgroup, so thirty seconds of budget takes a minute or more
of real time — and the run still reports as having used its budget, so the only
symptom is a queue that will not drain. It is now `planning.solver_workers`, and
it must equal the CPU the process is actually given. The Helm chart refuses to
render if the two disagree, and the compose file says so beside the limit.

Zero is refused rather than read as "decide for me": CP-SAT takes it as a
request for no search at all, returns immediately, and the run fails looking
like an infeasible plan.

## Qualifications and skills are hard constraints, not preferences

`_add_certifications` forces the assignment literal to zero for anybody who
does not hold what the work needs. The solver **cannot pay its way past it** the
way it can pay for travel: if nobody qualifies, the requirement goes unassigned
and the run fails. That is the intended answer — sending somebody unqualified
is worse than sending nobody, and the failed run says which qualification was
missing.

Requirements that need nothing are skipped entirely rather than given a
constraint everybody satisfies. Most work needs no qualification, and a
satisfied-by-everybody constraint per visit per assistant would grow the model
for no gain.

**Expiry is judged on the day of the visit, not the day of the solve.** A
first-aid certificate that lapses on Friday qualifies its holder for Thursday's
round and not for Monday's, and a plan built a fortnight ahead has to get that
right — checking against "now" would either send somebody out unqualified or
hold back work they can legitimately do.

**Every code, not any.** A requirement listing two diplomas means the person
needs both; reading it as "one of these" would send somebody to a visit half
qualified, which is the failure the whole field exists to prevent.

An **untyped** qualification satisfies nothing. `Certification.code` is what is
matched, and matching on the free-text name would let a spelling decide who is
qualified.

### Skills are the same constraint, kept separate on purpose

`_add_skills` does character for character what `_add_certifications` does, over
`required_skill_codes` and `Hca.holds_skills`: a hard constraint, requirements
needing nothing skipped entirely, expiry judged on the day of the visit, every
code rather than any, and an untyped declaration satisfying nothing.

Because the two produce the same literals, merging them would produce an
identical plan and cost nothing at solve time. **What it would cost is the
diagnosis** — and the log line. A run that placed nothing has to say whether
the answer is to hire somebody or to ask an assistant to finish filling in
their own profile, and those go to different people.

A certification does not satisfy a skill of the same code, and the reverse is
just as true. Holding the certification `TOILETTE` says nothing about having
*declared* the skill `TOILETTE`, and treating one as the other would send
somebody to a visit on the strength of a match nobody made.

### Where the requirement comes from

The builder resolves it once, per line, and hands the solver a finished list —
so the solver never needs the catalog, never holds a second lookup table, and
never has to know the inheritance rule exists. A line whose catalog entry has
vanished falls back to requiring **nothing**, at `WARNING`: an exception would
fail the whole run over one missing row, and inventing a requirement would
strand work nobody could be qualified for.

### The integrity nothing else can enforce

The codes live in JSON arrays on `intervention_types` and in nullable columns
on `certifications` and `skills`, and a foreign key can constrain neither the
first nor, usefully, the second. So `CertificationTypeService.assert_known` and
`SkillTypeService.assert_known` are both called by every writer of a
requirement, and both services' `delete` refuses to strand one — counting the
assistants who hold or declared the code and the services requiring it, and
naming both in the refusal. A requirement pointing at nothing fails every planning run it
touches, with a message that reads as a staffing problem when it was a typo.

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

`PlanningSettings` is a single row holding **six** values, edited through
`PUT /api/v1/planning/settings` and guarded on a manager:

| Value | What it bounds |
|---|---|
| `max_intervention_radius_km` | How far from home an assistant may be sent |
| `day_start_minute` / `day_end_minute` | The working day |
| `lunch_break_minutes` | How long the uninterrupted midday break is |
| `lunch_window_start_minute` / `lunch_window_end_minute` | When that break may fall |

The four time values were configuration-file constants until migration
0013. That made "we open at 08:00 now" a deployment rather than a decision,
which is not what *configurable by a manager* means. The solver reads all
six from this row, so the day it plans is the day somebody last agreed to.

The four are **checked against each other** on the way in, by the payload
and again by the stored model: a day must end after it starts, and the
lunch window must sit inside it and be wide enough to hold the break. Each
value is individually plausible and only wrong in combination — a
12:00–13:00 window with a 90-minute break is two settings that each look
fine and together make every day infeasible. Caught on the way in it is a
422 naming the conflict; caught by the solver it is a run that fails
against every visit with "no feasible slot", which names nothing.

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

### Scoped to the agency, first and above all

The delete is `WHERE company_id = … AND day BETWEEN …`, and the agency half of
that is newer than the rest. Until it was there, a run replanning one agency's
week deleted **every other agency's** visits in the same days and wrote none of
them back.

That was not a rare race. The broker gives each agency its own queue precisely
so their runs proceed at the same time, so two agencies planning overlapping
periods is the normal case — and calendars were lost routinely rather than
occasionally. The emptiest run is the most dangerous one: with no visits to
write back, an unscoped delete leaves nothing behind at all, which is also why
the agency is a parameter rather than read off the visits.

`QuoteRepository.list_schedulable` is scoped the same way, and has to be: that
is the input half. Unscoped, a run built one agency's week out of every agency's
accepted work and handed those visits to its own assistants — people who have
never met the customers and are not insured to attend them.

A transaction-scoped `pg_advisory_xact_lock` on the agency covers the rest. Two
runs for *one* agency each produce a complete, internally consistent plan, so
the later one winning is a correct outcome; what is not correct is one run's
delete landing between the other's delete and its inserts. The lock is taken
around the write and not around the solve — holding it across a thirty-second
budget would pin a pooled connection and buy nothing.

An assignment whose customer has no loadable address is dropped and reported at
ERROR rather than aborting the store: one unreachable customer must not cost the
whole workforce its week.

## Running it

`POST /api/v1/planning/runs` (administrator) records a `PENDING` run **naming
the caller's agency**, publishes `planning.run.requested`, and answers **202**
with the identifier to poll.

The agency is recorded on the run rather than resolved from `requested_by` when
a worker picks it up. That column carries no foreign key on purpose — an
administrator leaving must not take the record of what they ran with them — so
the account is allowed to be gone by then, and a run that could not name its own
agency would be one nothing could safely execute.

### Exactly one worker executes a run

A message is acknowledged only once its handler returns, so a worker killed
mid-solve leaves its run to be redelivered — and before the claim was a
compare-and-swap, both workers would solve the same period and each overwrite
the other's plan.

`PlanningRunRepository.claim` is an `UPDATE … WHERE status = 'pending'`. The
condition is evaluated by the database, so of two workers handed the same
message exactly one can match; the other updates no row and is told so.

**Losing is an ordinary outcome, not a failure.** The run is returned untouched
and the message is acknowledged, because another worker holds it or it has
already finished — and in both cases the right thing to do is nothing. Raising
instead would dead-letter a run that is being solved correctly somewhere else,
and put a red run in front of a manager for work that is going fine.

Three other requests end the same way, because each of them changes what the
solver has to place: cancelling a visit, deleting a customer, and deleting an
assistant. All four go through `queue_replan`, which records the run **before**
it is published — a caller handed a 202 must get back an identifier that is
already real, and a run published first could be picked up by a worker before
the row it names exists. A broker that will not take the message is an `ERROR`
and not a failure: the run stays `pending` for the next worker to find, and
raising would undo a deletion that has already happened for a reason unrelated
to it.

**The period a deletion replans is derived, not asked for.** A deletion from
the workforce grid has no calendar window to take one from, and the days that
actually need replanning are exactly the ones that person was due to work —
`future_period_for_hca` and `future_period_for_customer` return that span, or
`None` when there is nothing left. `None` means no run at all, and the endpoint
answers **204**: queueing one that would place the same visits in the same slots
costs thirty seconds of a worker and makes the calendar flicker for no reason.

The span is measured **before** the delete. Their visits go with them, so
asking afterwards would find nothing and replan nothing — leaving the rest of
the workforce with a calendar built around somebody who has gone.

The solve happens on the **planning worker**, which since the split is its own
deployment: it is the CPU-bound half, and sharing a process with the millisecond
notification fan-out meant the two scaled together. It used to be a FastAPI
`BackgroundTask` before even that, which lost the run on any restart and
occupied a web worker for the full thirty seconds. The message is acknowledged
only when the handler returns, so a worker killed mid-solve leaves the work for
the next one — and the claim above is what stops the next one duplicating it.

A worker draining must be given **longer than the solve budget** to stop.
Kubernetes' default grace period is thirty seconds, which is exactly the budget,
so a scale-down would `SIGKILL` mid-solve and the message would be redelivered
from the start. Both descriptions of the system say ninety: `stop_grace_period`
in compose, `terminationGracePeriodSeconds` in the chart, and the chart refuses
to render below sixty.

`execute_run` never raises for a solver problem — the failure is recorded on the
run, because a caller polling for a result needs to be told what went wrong, and
an exception disappearing into a background task would leave the run pending
forever.

## Tests

`tests/service/test_planning_solver.py` and `test_planning_constraints.py` drive
real solves over built scenarios and assert the placements and the diagnoses.
`test_requirement_builder.py` covers the translation from quote lines.

`test_planning_certifications.py` drives real solves over the certification
constraint: the qualified assistant gets the work, nobody qualified leaves it
unplaced, both diplomas are needed rather than either, a certificate that
lapses between two days changes the answer, and an untyped qualification counts
for nothing. It also covers the diagnosis ordering and the `field_employee`
filter. `test_planning_skills.py` is its twin over the skill constraint, and
adds the three cases only the pair can have: a certification does not satisfy a
skill, a visit gated on both needs one person holding both, and a missing
certification is reported ahead of a missing skill.
`test_person_deletion.py` covers the cascades and the replan scoping.

The GUI campaign's suite 28 does the same end to end: a service gated on a
qualification the seed deliberately leaves unheld, sold to a customer the run
creates, planned, and asserted to **fail** with the code in `error_message` and
`scheduled_count` still null — because a refused plan must not be a deleted
one.


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
