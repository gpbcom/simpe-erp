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
one CP-SAT model per DAY         solved concurrently, one search worker each
        │
        │   per day, two passes on the same model:
        │     1. minimise what is left out   ──▶ does the day fit at all?
        │     2. minimise travel, hinted     ──▶ only if pass 1 placed it all
        ▼
   merged into one plan
        │
        ├── feasible and complete ──▶ Intervention rows replace the period's plan
        └── anything unplaced ──────▶ the run FAILS, with a reason per visit
```

## A week is solved one day at a time

**No constraint links one day to another**, and that is a property worth
stating plainly because the whole shape of the solve rests on it. A
requirement belongs to exactly one day; `start` and `end` are minutes from
midnight with no day offset. The customer no-overlap is keyed by
`(customer, day)`. No-overlap, lunch and travel are built per (assistant,
day). The objective is a plain sum, so the minimum over a week is the sum of
the daily minima.

Solving the days apart is therefore an **exact decomposition, not a
heuristic** — it returns the same plan, only sooner. What it buys is search
space: a week is a set of independent sub-problems that CP-SAT cannot discover
for itself, so it explores their product. On a measured 150-visit,
12-assistant, 5-day instance the single model ran past a ten-minute wall-clock
net without proving anything. The same week now completes in under a minute
with every visit placed.

**Anything that couples two days breaks this.** A weekly hours cap, a rest
period between shifts, a fairness term across the week — each would make the
decomposition wrong, and wrong *quietly*, by returning worse plans rather than
by failing. Such a constraint has to go back into one model over the whole
period, and the speed has to be found somewhere else.

Because the days are independent, solving them at once cannot change the
answer. `PlanningService.solve_period` runs `planning.solver_day_concurrency`
of them on worker threads — CP-SAT releases the interpreter lock while it
searches, so this is real parallelism — each on its own shallow copy of the
service, because the model is built on instance attributes and two days
sharing one would overwrite each other's half-built model.

## Placing the work and shortening the rounds are two questions

Each day is solved twice, on the same model:

1. **Feasibility.** The objective is only how many visits were left out. That
   is a small integer with an obvious lower bound of zero, so the solver
   reaches and *proves* the answer quickly. Every travel constraint is still
   in the model — only the travel term of the *objective* is dropped. A pass
   that did not charge travel time would call a round feasible that nobody can
   drive, and that is precisely the plan kept if the second pass runs out.
2. **Optimisation.** Only if the first placed everything. It pins
   `sum(unassigned) == 0` — otherwise the solver discovers that the shortest
   round is the one skipping the furthest customer — hints itself with the
   first pass's plan, and minimises travel under `solver_optimisation_budget`.

If the second pass does not finish, **the first pass's plan is stored** and the
run records `is_optimised: false`. Nothing goes unscheduled for want of an
optimisation budget — every visit is placed either way, and only the *claim*
about the driving is withheld. The team planning screen shows that rather than
rendering it as an ordinary success, because a plan nobody can tell apart from
an optimised one is how a slow creep in travel goes unnoticed.

**Read the flag as being about the proof, not about the rounds.** On the
seeded agency it comes back false while the plan is almost certainly already
optimal: raising the optimisation budget from 5 to 15 returned the identical
256 minutes of travel and still could not prove it. Reaching the best plan is
easy here; showing that nothing beats it is not. That is why neither the
screen nor this page suggests turning the budget up — advice that sends an
operator to change a setting which does not help is worse than none.

`is_optimised` is nullable and **null is not false**: a run from before this
existed never asked the question.

A second pass that comes back INFEASIBLE is a **construction fault, not an
outcome** — the first pass's assignment satisfies that model by definition. It
is logged at ERROR and the unoptimised plan is kept, because a bug there must
not cost the agency its week.

## A run belongs to one team

A run rebuilds **one team's** week. Its workforce is that team's field
employees, its input is that team's accepted quotes, and its output replaces
that team's visits and nobody else's.

That split is **exact, not an approximation**, and for the same reason the
per-day split is: teams share no assistant and no quote, so solving them apart
returns the same plan as solving them together. The invariant it rests on is a
unique index — a person is on at most one team — and it is load-bearing rather
than tidy. Somebody on two teams would have two complete calendars written for
the same week by two runs, neither of which clears the other's visits, and
nothing anywhere would report the double booking.

## Three scopes: a team, a site, the company

A computation is asked for over one of three scopes, and every one but the
narrowest **fans out** into one run per team it covers. That is why
`POST /api/v1/planning/runs` answers with a *list*.

| Asked for | Covers | Who may ask |
|---|---|---|
| `?team_id=` | that team | its manager, or an administrator |
| `?agency_id=` | the teams of that site **the caller runs** | any manager, for their own |
| neither | every team of the company | **administrator only** |

A team is what a manager owns and a site is the level above it, so both are
theirs to rebuild. The site case is an **intersection** rather than the site's
roster: handing a manager every team at a branch office would make the branch a
way to rebuild a colleague's week without ever naming their team. A manager who
runs nothing at the named site gets an empty list rather than a refusal — an
honest answer to "plan my teams here" that says nothing about which teams the
site holds.

Naming no scope at all means the whole company, and that is an administrator's
act: it rewrites the calendar of every assistant employed, and no manager is
answerable for all of them. A manager who names nothing is **refused with a
403**, not quietly given their own teams — being told the company had been
re-planned when one team was would be worse than the refusal, and the message
names the two scopes they may use instead.

The route moved from administrator to manager because a run no longer rewrites
every calendar in the agency but exactly the ones a manager is responsible for.
Which team they may name is checked in the service, because a route guard can
only prove a rank.

**Both run *reads* are narrowed too**, and not only for confidentiality.
`GET /runs` is what the screen polls while a computation is in flight — it is
where "computing…" comes from and where the result is read — so leaving it at
administrator made a manager's button look like it did nothing at all: the run
was queued, solved and stored, and the page that asked for it never saw any of
it. `GET /runs/{id}` is narrowed because starting a run hands the caller its
identifier, so every manager holds real ones and could otherwise poll a
colleague's to learn how much of that team's week would not fit.

## Who the solver is even allowed to consider

`_workforce` narrows to the team first, and `_field_employees` is the single
point where the rest is decided. Before it existed the planner took **every** assistant
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
workforce screen must still show everybody. A query that quietly dropped the
office staff would make them look dismissed.

An empty pool is a legitimate answer, logged at `WARNING`: every requirement
comes back unassigned and the run fails, which is correct and traceable. What
must not happen is the filter silently falling back to the whole workforce.

## A partial plan is stored and named

**This reverses the rule the computation was originally built around**, and
the reason for the original is worth keeping in view: a calendar missing three
visits still looks like a calendar, nobody reads the run record to check, and
the visits quietly dropped are exactly the ones that end with somebody waiting
at their door.

The old answer was to refuse the whole week. That is safe and it is too blunt:
a real run came back with **one visit of ninety** unplaceable, and the agency
got no calendar at all plus a sentence quoting a solver status and a
configuration key. Eighty-nine good visits were withheld over one impossible
one, and nobody could act on the explanation.

So the plan is now stored, and the risk is answered by making the gap
impossible to miss rather than by withholding the week:

- the run ends **`partial`**, a status of its own — never `succeeded`;
- the screen shows it in **warning** colours, not as an ordinary success;
- and `unplaced_quotes` names **every affected quote**, its customer, each
  visit and why it did not fit.

**An empty solve is still refused**, and that is a different case. When the
solver returns nothing there is no plan to store, so the previous week stays
untouched exactly as before.

### What the report says, and in whose words

Grouped by **quote**, because that is the unit somebody can act on. A list of
thirty unplaced visits says something is wrong; "quote D-2648 for Jeanne
Vincent, one visit, the day was full" says who to telephone and what about.

No sentence is composed in the backend. `UnplacedQuote` carries the quote, the
customer and the diagnosed visits. The screen assembles the wording in the
reader's own language. A message built server-side would reach an English
operator in French, which the quote emails already taught this codebase once.

The reasons are rendered as plain statements — "nobody holds the qualification
it requires", "the day was full: travel, the break and the other visits left
no room" — rather than as the enum values the solver deals in. An operator is
not obliged to know what a deterministic budget is.

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
arbitrary.** A certification is obtained. A skill is merely declared. A visit
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

### What the solver status entitles the message to say

The per-visit reasons are only findings when the search finished. Three cases,
and they used to read identically:

| Status | What it means | What the run says |
|---|---|---|
| `OPTIMAL` | The search looked everywhere. This is the best plan there is | The per-visit reasons, in full |
| `FEASIBLE` | A plan was found and the budget ran out before proving it best | The size of the gap, and that it is **not** a proof |
| `INFEASIBLE` | Proved that no plan satisfies the constraints | Says so, and that it is a proof |
| `UNKNOWN` | The search stopped having found nothing | Says nothing was established |

**An unplaced visit costs `unassigned_penalty` — a hundred thousand against a
travel minute's one — so a solver that could place it would have.** Under
`FEASIBLE`, visits left out are therefore evidence the search ran out of budget,
not that the day is full. Reporting "travel, the lunch break and the other
visits that day leave no room for it" there sends a manager to move a customer's
hours to solve an arithmetic problem. Only `OPTIMAL` earns that sentence.

The specific reasons — radius, qualifications, skills, working day — survive
into every one of these messages. They are established outside the solver, so
they hold whatever it then did, and they are usually *why* the rest would not
fit around them.

### The input order is part of the determinism

`random_seed` and `max_deterministic_time` only reproduce a run **given an
identical model**, and the model is built by walking the rows
`list_schedulable` returns. That query had no `ORDER BY`, and PostgreSQL
guarantees no ordering without one — so the same week could be handed to the
solver as two different variable orderings, the search would stop in a
different place, and a different number of visits would come back unplaced. The
same week really did report two unplaced and then one. It now orders by the
primary key, which is the only column certain to break every tie.

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

### Three budgets, spent once per day each

**Every figure here is per day, not per period.** The week is one model per
day, so a budget of five is five for Monday and five again for Tuesday. It was
150 when a single model covered the whole period, and leaving it there through
the decomposition made a five-day week cost five times 150 — the change that
was meant to make planning faster briefly made it three times slower. That is
the kind of mistake this section exists to prevent.

`solver_deterministic_budget` ends the **feasibility** pass and
`solver_optimisation_budget` ends the **travel** pass. Both count solver *work
units* rather than seconds, which is the whole point: a wall-clock budget stops
wherever elapsed time happens to land, so a loaded machine explores less and
returns a worse plan for the same week.

Sized by measurement on a 150-visit, 12-assistant, 5-day instance, one worker
per day:

| per-day budget | outcome |
|---|---|
| 2.0 | two days found nothing at all (UNKNOWN) |
| 5.0 | every visit placed, whole week under a minute |

Five is therefore the floor rather than a target. Raising the feasibility
budget buys nothing once the week reliably fits, and — measured on the seeded
agency — raising the optimisation budget from 5 to 15 bought nothing either:
the same 256 minutes of travel, still unproved. The budget is not the lever it
looks like; proving optimality is simply much harder than reaching it.

`solver_time_limit_seconds` is a **safety net, not a budget**, and it bounds
one day rather than the week. It catches a pathological instance that would
otherwise grind for a very long time inside its allowance. A solve that reaches
it has stopped being reproducible and says so at WARNING.

**These two measure different things, so nothing makes them agree by
construction — and a pair that disagrees is silent.** The Helm chart shipped
exactly that mistake: it pinned the net at `30.0` and never set the deterministic
budget at all, so a cluster fell back to the model default and then cut every
solve off a fraction of the way into the search it needed. The plan came back
with visits unplaced that a full search places, and the only trace was one
WARNING per run. Both `infra/chart` and
`tests/models/configuration/test_solver_budget_is_reachable.py` now refuse a net
below twenty times the budget. That floor has been calibrated against the
wrong thing twice — first drawn from a one-worker measurement while the shipped
configuration ran eight, so it passed the very configuration it exists to
catch: a net of 900 against a budget of 100, which truncated every search and
left a 95-visit week one visit short at status FEASIBLE.

`solver_workers` is how many search threads CP-SAT may run **inside one day's
model**, and `solver_day_concurrency` is how many days run at once. The CPU a
run demands is **the product**, not either alone, and it must equal the cores
the process is given. Under a container CPU *limit* more threads than cores
does not merely fail to help: the kernel throttles the whole cgroup, so the net
arrives after less real search — and the run still reports as having used its
allowance, so the only symptom is a queue that will not drain. The Helm chart
refuses to render when the product and the limit disagree, and the compose file
says so beside the limit.

Workers is now **one**. The models are one day each and small enough that a
second thread buys little, and a single worker is what makes a re-planned week
return the same answer instead of a different one. Parallelism comes from the
days, which cannot race because they are independent problems — so the
reproducibility that eight workers cost is recovered without giving up the
speed.

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

Changing them does not re-plan anything. They apply to the next run. Silently
recomputing this week because somebody adjusted a radius would move assistants
who have already been told where to go.

## Storing the result

`replace_for_period` deletes and re-inserts inside **one transaction**, scoped to
the period rather than the run — so re-planning one week does not disturb the
week after it, which a different run produced. A caller refreshing mid-replan
sees the old plan or the new one, never a blank week.

### Scoped to the agency and the team, first and above all

The delete is `WHERE company_id = … AND team_id = … AND day BETWEEN …`, and both
scoping halves are newer than the rest. Until it was there, a run replanning one agency's
week deleted **every other agency's** visits in the same days and wrote none of
them back.

The team half is the identical bug one level down, and now the **likelier** of
the two: two agencies replanning the same days is a coincidence, while two teams
of one agency doing it is an ordinary Monday — each team's manager re-plans
their own week. Without the team in the delete, the second manager to press the
button blanks the first one's calendars and writes none of them back.

The lock stays keyed on the **agency**, not the team. Two teams' runs touch
disjoint rows, so serialising them costs a moment and keeps the existing
guarantee unchanged. Keying it per team would leave the delete's correctness
resting on the scoping alone, and the scoping is what this section exists to say
has been wrong before.

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
message exactly one can match. The other updates no row and is told so.

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

`POST /api/v1/planning/runs?period_start=&period_end=` — **manager-and-above**,
like listing and reading runs. It answers **202** with one `pending` run per
team in scope: the solve is CPU-bound, runs on a worker with a 30-second budget,
and reaches the worker over the broker.

Nothing in the application ever called it. The endpoints existed, the worker
consumed them, and there was no control anywhere — so a freshly seeded stack had
no planning, no way to ask for one, and nothing on any screen to say why. The
team-planning screen now carries the button and, beside it, a **scope picker**
listing the caller's teams, the sites they run a team at, and — for an
administrator alone — the whole company. A manager opens on their site, which is
the widest thing they may ask for. A manager who runs no team anywhere gets a
disabled button, because a control that can only answer 403 is worse than one
that is plainly unavailable.

The screen polls while a run is in flight and stops when it finishes. Asking for
one invalidates the *visits* as well as the runs: they are written by the
worker, behind the screen's back, so nothing else would refresh them — and being
told "75 visits planned" above an empty list is worse than being told nothing.
Both halves of that had to be true of the *manager's* session too, and for a
while neither was: the polling query was gated on the administrator role and the
invalidation named only the runs. A manager could press the button, have the
work queued, solved and stored, and watch a page that never changed — which is
indistinguishable from a planning that was never computed.

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
