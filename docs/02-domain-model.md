# 02 — Domain model

Every model is a Pydantic class in `backend/models/src/models/`, with per-field
validators that raise its own `MT*` exception family. Validation runs on the way
**in and out** of the database, so a value that stopped being valid is caught at
the boundary rather than propagating.

## The shape of the business

```
Company ──┬── Agency ──┬── AgencyMember  (user | hca)
          │            └── Team ──┬── TeamMember  (user | hca)
          │                       ├── TeamDocument
          │                       └── PlanningRun ──── Intervention
          ├── Hca ──────── AvailabilitySlot
          │     └───────── Certification, Skill, DrivingLicense
          └── User (account)

Certification ┈┈code┈┈▶ CertificationType ◀┈┈code┈┈ InterventionType
                                          ◀┈┈code┈┈ QuoteLine
Skill         ┈┈code┈┈▶ SkillType         ◀┈┈code┈┈ InterventionType
                                          ◀┈┈code┈┈ QuoteLine

Customer ──── Quote ──── QuoteLine ──── InterventionType
                 └────── QuoteTypeWeekAggregate


BillingRun ───── Bill ──── BillLine ┈┈quote_line_id┈┈▶ QuoteLine
                   │                ┈┈intervention_id┈▶ Intervention
                   └──▶ Customer  (RESTRICT)

Notification ──▶ User
```

## People

Every person the system holds descends from **`Person`**
(`models/base/person.py`): an identifier, a given and family name, a telephone
number, an email address, a postal address and the two timestamps, with the
validators for all eight and a `full_name()` that composes the two names.
`Hca`, `Customer`, `HcaApplication` and `User` all extend it.

It exists because those four had four copies of the same rules, spelled four
slightly different ways, so a fix to one of them was a fix to one of them. The
per-model exceptions survive the move: each subclass declares `INVALID_ID`,
`INVALID_EMAIL` and so on as class attributes, the shared validator raises
`cls.INVALID_*`, and Pydantic binds `cls` to the concrete subclass — so an
`Hca` still raises `MTHcaInvalidEmail` and a `Customer` still raises
`MTCustomerInvalidEmail`. That is not tidiness: the API's exception-to-status
map is keyed on those classes.

Where a subclass genuinely differs it **overrides**, and says why in the
docstring — `HcaApplication` lower-cases the email because it becomes a
sign-in, and parses its own timestamps; `User` does both of those and relaxes
two more rules, below.

**`PortraitHolder`** (`models/base/portrait_holder.py`) is a mixin beside it,
carrying `photo_url`, the object-store key prefix and the check that a URL was
issued by this application. `Hca` and `User` inherit it; `Customer` and
`HcaApplication` do not, which is the whole reason it is a mixin rather than
part of `Person` — folding it in would publish an empty field on a customer and
on a job application. The rule it holds is a security one: both holders render
the image wherever the person appears, so a third-party URL would report every
viewer to whoever hosts it, and two copies of that check are two chances for
one of them to be relaxed.

**`Hca`** — a home care assistant. Identity, address, contract, qualifications,
an optional driving licence, an optional photograph, and declared absences.
`can_drive()` decides which travel speed the planner uses for them;
`is_available_on(day)` is what an absence removes them from; and
`holds_certifications(codes, day)` / `holds_skills(codes, day)` are what a
gated intervention asks before it can be given to them.

**`working_weekdays` and `availability` are two different questions**, and
keeping them apart is deliberate. The first is the *recurring* pattern —
"never Wednesdays" — and the second is *dated*: this fortnight's leave.
Both stop the planner scheduling somebody, and `is_schedulable_on(day)` is
the conjunction the solver actually uses. They stay separate because only
one of them ends when the person comes back, and because the unplaced-work
report has to tell a manager which they are looking at: hiring cover for a
Wednesday and waiting out a fortnight's leave are different actions.
A week naming no day is refused rather than read as a request for the
default — clearing every box is a statement, and its two readings are
opposites. Declared by the assistant themselves and visible to their
manager, on the same ownership check the absences use — so a manager or an
administrator sets anybody's, including their own.

**`DEFAULT_WORKING_WEEKDAYS` is Monday-to-Friday, and it is a default rather
than a rule.** `Weekday` carries all seven days, `WorkingDaysRequest` accepts
any of them, and the planner asks `works_on_weekday` rather than testing for a
weekend — so Saturday and Sunday are ordinary working days for anybody whose
declared week names them. The distinction matters because it is invisible: a
record nobody has edited shows both greyed, which reads exactly like a rule
forbidding them.

**`field_employee` decides who the planner may schedule at all**, and it
**defaults to `True`**. The default is the whole reason the field could be
added safely: every assistant record that existed before it did was, by
definition, somebody the planner was already free to schedule, so defaulting to
`False` would have emptied the workforce on the deployment that introduced it
and failed every planning run until somebody ticked a box they had not been
told about.

It is a boolean on the *person*, not a check on their account's role. Who goes
out is not what an account may do: a manager who covers rounds and an assistant
on office duties are both ordinary, and neither is expressible as a `UserRole`.
Only a manager or an administrator may change it — for anybody, including
themselves — which is enforced by the field living on the manager-gated
`EmploymentUpdateRequest` and being absent from `HcaProfileUpdateRequest`.

**`Customer`** — somebody served. Identity, address, and a
`RegistrationStatus`, which is **`prospect` by default**: a newly registered
household is one the agency has taken details for, not one it has agreed to
serve.

`RegistrationStatus.can_be_scheduled()` is the one question the planner asks,
and only `active` answers yes. A prospect may be quoted — that is what a
prospect is *for* — and their accepted, priced, perfectly routable work still
produces no requirement, because sending somebody to the door would be the
error, not the omission. `PlanningService.build()` skips it per quote, counts
the lines it skipped and names the quote at WARNING, so the work is visibly
excluded rather than silently missing. This is deliberately **not** the "partial
plan" a run refuses over: that work was never in scope.

`is_active()` is a narrower question and keeps its exact meaning — *the status
is `active`*. With three states the two questions came apart, and overloading
`is_active()` would have wrongly implied a prospect cannot be quoted.

`POST /customers/{id}/promote` is the one transition with a rule: only from
`prospect`, refused with **409** from anything else. The general
`PATCH /{id}/status` still reaches every state, including back to `prospect`
when a signature turns out never to have arrived.

**`User`** — an account, and a `Person` like the rest. On top of the shared
record it carries `role`, an optional `hca_id` binding it to an assistant
record, `company_id`, `must_change_password` and an optional `photo_url`.
`owns_hca(id)` is the row-level check the planning and self-service routes rest
on.

It relaxes two of the base's rules, both because an account is a *credential*
rather than a contact record:

| Rule | On a person | On an account |
|---|---|---|
| `phone_number`, `address` | Required — an assistant's address is a routing depot, a customer's is where the care happens | Optional, and not stored at all. A manager has neither, and no screen asks them for one |
| `first_name` | Required | May be empty. A mononym or a service account has no given name, and its whole name sits in `last_name` |

**The display name is two columns.** `users.full_name` became `first_name` and
`last_name` in migration `0014`, and `full_name()` recomposes them. Nothing
above the model had to change: every caller still passes a single
`full_name="Claire Bernard"`, which a `mode="before"` model validator splits on
the **first** space, and `UserResponse` still publishes `full_name` — so the
API shape, the front-end and the emails are exactly as they were.

Splitting on the first space rather than the last is what makes the round trip
exact: `"Jean Pierre de la Tour"` stores `"Jean"` and `"Pierre de la Tour"` and
reads back identical, where a last-space split would file the same person under
the surname `"Tour"`. A name with no space at all goes wholly into `last_name`,
which is the reason an account may have an empty given name and no other person
type may.

One trap worth knowing: `full_name` is a **method** on an account now, so
`user.model_copy(update={"full_name": ...})` no longer renames anybody — it
shadows the method with a string, and the failure surfaces as
`'str' object is not callable` somewhere else entirely. `User.name_parts()` is
the supported way to go from a display name to the two halves, and
`AuthService.update_account` uses it.

The portrait is on the *account* as well as on `Hca`, and the two are not one
field split in half. `Hca.photo_url` is the pin the manager's map draws, and it
belongs to the person being scheduled; `User.photo_url` belongs to the
credential, so a manager and an administrator have one too — before it existed
they had nowhere to put a face at all. When an account is bound to a record the
service writes both from one upload, because it is the same photograph of the
same person. Both validate that the URL carries the object store's own key
prefix, so neither can be pointed at a third-party address.

**Everybody belongs to exactly one agency**, and since `0016` so does
everything the planner touches. `company_id` is required on `User` and on `Hca`
alike — administrator, manager and assistant — and `NOT NULL` in both tables
since migration `0008`. It was optional while companies were newer
than the rows pointing at them; nothing keeps that true now. An account without
an agency is covered by no per-company scoping and produces events that cannot
be routed to a queue, so the state is refused rather than stored and puzzled
over later.

### What the planner is scoped by

`Quote`, `PlanningRun` and `Intervention` each carry a **required** `company_id`
as of migration `0016`. These are the three the planning computation reads and
writes, and until each named an agency the computation had no way to tell whose
work it was scheduling: a run selected every agency's accepted quotes and then
deleted and rewrote every agency's visits in its period.

| Model | Where the agency comes from | Why it is not derived |
|---|---|---|
| `Quote` | the caller's credential, at creation | `authored_by` is nullable — an author who leaves must not take their quotes with them — so the join it would replace passes through a column that is allowed to be empty |
| `PlanningRun` | the caller's credential, at request | `requested_by` carries no foreign key, so the account may be gone by the time a worker picks the run up |
| `Intervention` | the run that produced it | it is deleted in bulk by agency and day, so one that did not name an agency would escape every replacement for ever |

**Required rather than optional, on all three.** What makes the scoping a
property rather than a discipline is that there is no state in which one of
these records exists without naming an agency.

The agency is never something a payload can set. `POST /quotes` takes a
`QuoteCreateRequest` — reference, customer and lines, and nothing else — because
a caller who could name an agency could write a quote into another one and have
that agency's assistants sent out to deliver it. The same model closed a second
hole on the way past: the route used to accept a whole `Quote`, so a payload
could also carry `status="accepted"` and `validated_by`, approving its own quote
in somebody else's name.

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

**`Certification`** — one qualification somebody holds. A free-text `name`,
an optional `code` naming the catalogue entry it instantiates, an issuer and
two dates. `satisfies(code, day)` is the match, and it answers `False` for an
**untyped** qualification: a free-text name is a record of something somebody
holds, not a claim the agency can match against, and treating one as a match
would let a spelling decide who is qualified.

The code is optional, and the free-text name stays beside it, because the
catalogue arrived after the records did. A qualification typed before it
existed is still a qualification somebody holds; making the link mandatory
would have meant inventing a catalogue entry for every distinct spelling
already stored, and getting some of them wrong.

**`CertificationType`** — the catalogue. A `code`, a `label`, a description and
`is_active`. **The code is the contract, not the label**: an assistant's stored
qualification and an intervention type's requirement are matched on it, so
renaming the label is cosmetic while changing the code would silently
disqualify everybody who held it. That is why the two are separate fields, why
the code is restricted to unaccented letters, digits, hyphens and underscores,
and why no edit payload carries it at all.

Retired with `is_active`, never deleted — like `InterventionType`, and for the
same kind of reason: a stored qualification still names its code, and removing
the row would leave somebody holding a certification nothing could describe.
Deleting *is* offered while nothing refers to the entry, which in practice
means the morning it was added by mistake.

**`Skill`** — one thing somebody says they can do. The same shape as a
`Certification` — a free-text `name`, an optional `code`, an issuer and two
dates, with the same `satisfies(code, day)` — plus **an `id`**, which a
certification does not have.

That one extra field is the whole difference in how the two are written. A
certification list is replaced wholesale by the employment form, so no
individual row is ever addressed. A skill is added one at a time by its owner
and removed one at a time by its owner, a manager or an administrator, and
every one of those operations names a single record. Matching on the fields
instead cannot tell two skills entered under the same name apart.

There is deliberately **no `hca_id`**. The owning assistant comes from the
route and is applied by the repository, so a payload cannot file a declaration
against a colleague — the absence *is* the control, the same way
`AccountUpdateRequest` carries no role.

### Who writes what, and why the two are not one field

| | Certification | Skill |
|---|---|---|
| What it claims | What somebody was **awarded** | What somebody **can do** |
| Who records it | A manager, through `PATCH /hcas/{id}/employment` | Its owner, through `POST /me/hca/skills` |
| Who removes it | A manager, by resending the list | Its owner, a manager or an administrator |
| Approval | Recorded by somebody who already decides | None — the supervisors are **notified** instead |
| Unplaced reason | `missing-certification` | `missing-skill` |

An assistant who could grant themselves a diploma could be routed to work they
are not trained for. An assistant who cannot say they speak Portuguese is one
the agency does not know it has. Both are real failures, and they point in
opposite directions, which is why the two live in separate tables under
separate permissions rather than in one list with a flag.

The declaration takes effect **immediately**. Approval-first would leave
somebody off the visit they are the right person for while a form sat in a
queue; instead every manager and administrator gets a `skill-added`
notification and any of them can withdraw it before the next run acts on it.

**`SkillType`** — the skill catalogue, character for character the twin of
`CertificationType`: a `code`, a `label`, a description and `is_active`, the
code immutable and restricted to unaccented letters, digits, hyphens and
underscores, retired rather than deleted. **The catalogue is a manager's even
though the declarations are not** — a workforce able to invent catalogue
entries would produce a list nobody could require anything from.

**`HcaApplication`** — somebody asking to be hired, before they are an `Hca`.

## Everybody can be deleted, and something has to happen next

Deleting a person used to be refused wherever it mattered. A customer with any
quote answered 409 and was told to be *stopped* instead; an assistant with a
sign-in account answered 409 because the foreign key would not have it. Both
refusals were defensible and both were wrong in the same way: they left no way
at all to remove a household entered by mistake, or an assistant raised in
error, or the fixtures a test campaign is obliged to clean up after itself.

So each deletion now **cascades what cannot outlive the person**, and then
**replans what they were due**:

| Deleting | Takes with it | Then |
|---|---|---|
| `Customer` | Every quote written for them, and the visits scheduled from them | Replans their remaining days |
| `Hca` | The sign-in account bound to them | Replans their remaining days |
| `User` | Nothing | Nothing |

The account goes with the assistant because an account whose `hca_id` names
nothing cannot pass the row-level planning check and cannot be repaired through
any screen. It is removed **first**, and through `AuthService`, so that
service's own refusals still hold: nobody deletes their own account, and the
last administrator cannot be deleted at all. Doing it in the other order would
remove the assistant and *then* discover the account could not go — leaving
exactly the orphan this avoids. Both writes share one transaction, so a refusal
rolls the whole thing back.

Deleting a `User` replans nothing, and that is not an oversight. An account is
not scheduled; the assistant record is. Removing one cannot change a calendar.

**Stopping a customer is still the right answer** for one who was really served
and has really left — it keeps what was billed and who agreed to it. Deletion
is for the records that were never part of that history, and the screen that
offers it counts the quotes first.

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

Its `required_certification_codes` **distinguishes three states**, and the
third is why the field is nullable rather than a plain list:

| Value | Means |
|---|---|
| `null` | Whatever the catalog entry requires |
| `["DEAES"]` | These, instead of the catalog's |
| `[]` | This hour needs no qualification at all |

The last is a real answer somebody has to be able to give when the catalogue's
default is wrong for one customer, and collapsing it into `null` would silently
reinstate a requirement the person writing the quote had deliberately removed.
`effective_certification_codes(catalog_codes)` resolves the fallback in one
place, the way `InterventionType.effective_hourly_rate_ht` does for the rate.

`required_skill_codes` carries the same three states, overridden
**independently**. A line that needs the catalogue's diplomas but no particular
skill is an ordinary thing to want, and one nullable field covering both would
make it inexpressible.

**`InterventionType`** — a catalog entry: a name, a code, a category that
decides the VAT rate, a base hourly rate, and the qualifications the work
requires. Retired with `is_active` rather than deleted, because a quote issued
last year still references it.

`required_certification_codes` and `required_skill_codes` are both **empty by
default**, so adding either changed nothing about work already being sold. A
default that required something would have failed every planning run the moment
it shipped, which is a migration failure wearing a solver's clothes.

They are two lists rather than one. Both become the same kind of hard
constraint, so merging them would produce an identical plan — what it would
cost is the diagnosis. A run that placed nothing has to be able to say whether
the fix is a hire or a profile somebody has not filled in.

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

## Billing

Four tables, written by migration `0023_billing`: `bills`, `bill_lines`,
`billing_runs` and `billing_settings`.

**`Bill`** (`bills`) — one invoice, for one customer, covering one period. It
carries its own totals (`total_ht`, `total_vat`, `total_ttc`), the dates that
matter commercially (`issued_on`, `due_on`, `paid_on`), and a `BillStatus`
walking `to-be-validated → accepted → waiting-payment → paid`.

**The customer's name and address are copied onto the invoice**, exactly as an
`Intervention` copies them. Same reason, with more force: an invoice is a
document that was *sent*, and a household that moves house must not retroactively
change the address on a bill already in an accountant's file. `customer_id` is
still there, and its foreign key is `ON DELETE RESTRICT` — the one relationship
in the schema that refuses to cascade. Everything else about a customer can be
erased with them; their invoices cannot, because deleting them would destroy the
agency's accounting record.

Three unique indexes carry three separate rules:

| Index | Rule it enforces |
|---|---|
| `ix_bills_number_unique` on `number` | No two invoices share a human-facing number |
| `ix_bills_sequence_unique` on `(company_id, sequence_year, sequence)` | The yearly series has no gaps and no duplicates, per agency |
| `ix_bills_customer_period_unique` on `(customer_id, period_start, period_end)` | **A customer is billed once for a period.** This is what makes a re-run safe: a second run over March cannot double-bill, because the database refuses the row |

That third one is the load-bearing one. It is why the billing run can be
retried after a partial failure without anybody reconciling by hand.

`number` and `sequence` are separate fields on purpose. The sequence is the
integer the law cares about — unbroken, per year, per agency — and the number is
what a human reads. Deriving one from the other at read time would make a
formatting change rewrite invoices that have already been sent.

**`BillLine`** (`bill_lines`) — one charge. `ON DELETE CASCADE` from its bill: a
line means nothing without the invoice it is on.

It points at `quote_line_id` (what was sold) and optionally
`intervention_id` (the visit that delivered it), but neither is a foreign key
with teeth — the line carries its own `name`, `service_date`, `duration_minutes`,
`hourly_rate_ht`, `vat_rate` and `hca_full_name`, so the invoice still prints
correctly after a quote is re-priced or a planning run is deleted and recomputed.
`intervention_id` is nullable because a service can be billed as sold without a
visit ever having been planned for it.

The VAT rate is **on the line**, not looked up. See the chapter's closing note:
the same service is necessity care for one customer and comfort care for
another, so the rate depends on who was billed and when — and an invoice must
reproduce the tax it actually charged.

**`BillingRun`** (`billing_runs`) — one execution of the billing computation,
the exact counterpart of `PlanningRun`. It records `reference_date` (the day
that decides the period), the resolved `period_start`/`period_end`, the
`bill_ids` it produced and the `failed_customer_ids` it could not bill.

`BillingRunStatus` has five values, and `partial` is the interesting one:
`pending → running → succeeded | partial | failed`. **This is where billing
deliberately differs from planning.** A planning run that cannot place
everything fails outright, because a half-built round sends somebody to the
wrong door. A billing run that cannot bill three customers out of ninety
records those three in `failed_customer_ids`, keeps the eighty-seven invoices it
did produce, and reports `partial` — invoices are independent of one another,
and withholding eighty-seven correct ones to punish three failures would cost
the agency a month of cash flow.

**`BillingSettings`** (`billing_settings`) — the agency's invoicing rules, and a
**singleton row**, like `PlanningSettings`: `periodicity`, `payment_terms_days`,
`late_penalty_multiplier`, `recovery_indemnity_eur` and `escompte_offered`. The
last three are French statutory mentions that must appear on every invoice;
they live in configuration rather than in a template so that a change in the law
is a form field rather than a deployment.

Settings are read when a bill is *generated* and then copied onto it —
`due_on` is a stored date, not `issued_on + payment_terms_days` computed at
read time. Changing the terms must not silently re-date invoices already sent.

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
| `UserRole` | `hca` < `manager` < `admin`, with `has_at_least()`; plus `customer`, which is **off the ladder** — `rank()` refuses it. See [11](11-security.md#the-customer-is-not-a-rung-of-the-ladder) |
| `AccountOrigin` | `self-registered`, `created-by-staff` |
| `RegistrationStatus` | `active`, `prospect`, `stopped`, with `can_be_scheduled()` |
| `ContractType` | `cdi`, `cdd`, `interim`, `internship` |
| `ServiceCategory` | `necessity` (VAT 5.5 %), `comfort` (VAT 20 %) |
| `QuoteStatus` | `draft`, `pending-validation`, `sent`, `accepted`, `rejected`, `expired` |
| `InterventionStatus` | `planned`, `confirmed`, `completed`, `cancelled` |
| `AvailabilityKind` | `holiday`, `day-off`, `sick-leave`, `training`, `unavailable` |
| `PlanningRunStatus` | `pending`, `running`, `succeeded`, `failed` |
| `AgencyType` | `hq`, `warehouse`, `office`, with `is_headquarters()` |
| `MemberKind` | `user`, `hca` — which kind of record a membership names |
| `UnplacedReason` | `out-of-radius`, `not-a-working-day`, `no-assistant-available`, `outside-working-day`, `missing-certification`, `missing-skill`, `customer-conflict`, `no-feasible-slot` |
| `HcaApplicationStatus` | `pending`, `approved`, `rejected` |
| `BillingPeriodicity` | `weekly`, `monthly`, `yearly` |
| `BillStatus` | `to-be-validated`, `accepted`, `waiting-payment`, `paid`, with `is_terminal()` |
| `BillingRunStatus` | `pending`, `running`, `succeeded`, `partial`, `failed`, with `is_terminal()` |
| `NotificationKind` | `quote-submitted`, `quote-validated`, `quote-refused`, `planning-completed`, `skill-added` |
| `EventRoutingKey` | `quote.submitted`, `quote.validated`, `quote.refused`, `planning.run.requested`, `planning.run.completed`, `company.created`, `skill.added`, `notification.created` |
| `Weekday` | `monday` … `sunday` |
| `Language` | `fr`, `en` — what an account reads, and what its emailed documents are written in |
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
| 0008 | `company_id` made `NOT NULL` on accounts and assistants |
| 0009 | The VAT category moved onto the quote line |
| 0010 | Quote interruption and renewal |
| 0011 | An account's own photograph |
| 0012 | The certification catalogue, its requirements, and `field_employee` |
| 0013 | Per-assistant working days, and the agency's working hours |
| 0014 | `users.full_name` split into `first_name` + `last_name`, so an account is a `Person` |
| 0015 | `users.language`, so the emailed quotes can be generated in it |
| 0018 | The agency's legal identity: form, share capital, RCS, VAT number, telephone |
| 0016 | `company_id` on quotes, planning runs and interventions — the planning computation's own scoping |
| 0017 | The skill catalogue, self-declared skills, and their requirements |
| 0019 | The agency's bank details and its logo |
| 0020 | Whether a planning run's solution was proven optimal |
| 0021 | The quotes a planning run could not place |
| 0022 | Planning feedback recorded on the quote |
| 0023 | Billing: `bills`, `bill_lines`, `billing_runs`, `billing_settings` |
| 0024 | Per-customer billing periodicity, overriding the agency's |
| 0025 | `users.customer_id`, so a household can sign in to their own space |
| 0028 | `agencies`, `agency_members`, `teams`, `team_members`, `team_documents`; `team_id` on `quotes`, `planning_runs` and `interventions` |

The link in 0025 runs **both ways**: a customer account must carry one and no
other role may. A staff account holding a `customer_id` would satisfy the staff
guards *and* resolve to one household — an account on both sides of the boundary
at once — so `User.check_customer_link` refuses to build it.

0028 is the one with the largest backfill, and it is **not optional**. Quote
creation now refuses when no team can be determined, so a deployment that
upgraded without it could not write a quote at all. The migration therefore
gives every existing company a head office copied from the company record, one
team named *"Equipe principale"* run by its earliest manager, and puts every
account, assistant, quote, run and visit into that team — *before* the three
`team_id` columns are made `NOT NULL`.
`tests/storage/test_migration_0028_backfill.py` asserts each step, including
that the database itself refuses a second head office.

The widening in 0006 is the one to remember. `status` was `String(16)`, sized
when `accepted` was the longest value; `pending-validation` is eighteen
characters. SQLite truncates silently and PostgreSQL errors — so without that
migration the feature passes the whole test suite and fails on first contact
with the real database.

The split in 0014 is the one with a data hazard, and it is handled in the
backfill rather than left to chance. Names are split on the **first** space so
`full_name()` reproduces the original exactly; a name with no space at all goes
wholly into `last_name`, because inventing a given name for a mononym or a
service account would be worse than leaving the column blank. Both columns land
with a server default of `''` so the constraint can be added before the backfill
runs, and the default is dropped afterwards. `tests/storage/test_migration_0014_backfill.py`
asserts each case, including that the downgrade recomposes what was there.

**0018 backfills nothing, and that is the point.** Its five columns are all
nullable because none has a safe value to invent: a share capital written as
zero would be a false declaration, and an RCS entry copied from the SIRET a
wrong one. An agency that has not filled them in prints without them — the
quote joins only the parts that are set. That is the opposite of what 0012,
0013 and 0015 do, and for the opposite reason: those columns had a correct
answer for every existing row, and these have none.

**0015 backfills every account to French**, with a server default that is
then dropped — the shape 0012 and 0013 both use. The preference lived in the
browser until that revision, so the migration cannot see what anybody had
chosen; French is what the agency, its contract types and its holidays are,
which makes it the safe reading rather than merely the common one. An
English backfill would have sent every French agency's customers an English
document on the deployment that was only supposed to make the setting
reachable. `tests/storage/test_migration_0015_backfill.py` asserts it.

**The two backfills in 0013 disagree on purpose.** The four working-day
columns on `planning_settings` are backfilled with the values the
configuration file shipped, so making them editable does not move the
agency's day. `hcas.working_weekdays` is backfilled with **all seven days**,
not the Monday-to-Friday a *new* assistant defaults to: every row that
existed before the column did was schedulable on any day the planner had
work for them, and narrowing them here would cancel weekend rounds nobody
asked to cancel — visible only as a run that suddenly cannot place a
Saturday visit. `tests/storage/test_migration_0013_backfill.py` asserts
both, and pins the divergence so it is not tidied away.

The two defaults in 0012 are the load-bearing part of that one. `field_employee`
is added with a server default of true which is then **dropped**: the default
backfills every existing row, and dropping it afterwards keeps the value the
application model's to decide rather than the database's.
`intervention_types.required_certification_codes` is backfilled to an empty
array before it is made `NOT NULL`, so no service already being sold suddenly
requires something nobody holds. The quote-line column stays nullable, because
`NULL` there means "inherit" and is not the same statement as `[]`.

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
