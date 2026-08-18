# 03 — API reference

**74 paths, 100 operations.** The live schema is at `/openapi.json`, rendered at
`/docs`, and a copy is committed at the repository root so CI can fail on drift.

Base URL: `http://localhost:8000` in development; `/api` behind nginx in
production, where the front-end is same-origin.

## Reading the guard column

| Guard | Passes for |
|---|---|
| — | Anybody, no credential needed |
| `current` | Any signed-in account |
| `manager` | Manager **or** administrator (`has_at_least`) |
| `admin` | Administrator only |
| *own* | Any signed-in account, narrowed to their own records by the service |

Every error body is `{"detail": "..."}`. 5xx messages are replaced with generic
text; 4xx carry the exception's own message.

## Authentication — `/api/v1/auth`

| Method | Path | Guard | |
|---|---|---|---|
| POST | `/register` | — | Creates an **assistant** account. The role is not taken from the payload and cannot be |
| POST | `/login` | — | → `{access_token, token_type, expires_in}` |
| GET | `/me` | current | The account behind the credential |
| POST | `/password` | current | Changes it, and clears `must_change_password` |
| POST | `/accounts` | manager | Creates a staff account, returning a one-time password **once** |
| POST | `/stream-token` | current | A 60-second token scoped for the SSE stream |

There is **no refresh token**. The access token lives 720 minutes and the client
signs in again.

## My account — `/api/v1/me`

The assistant's self-service surface. The record acted on always comes from the
credential. No path parameter names it.

| Method | Path | Guard | |
|---|---|---|---|
| GET | `/hca` | own | The caller's own assistant record |
| PATCH | `/hca` | own | Contact details and address. **No `contract_type`, no `certifications`** — the payload has no such fields |
| POST | `/hca/skills` | own | Declares a skill about yourself. 201, and every supervisor is notified |
| DELETE | `/hca/skills/{id}` | own | Withdraws one of your own. 404 whether absent or not yours |
| GET | `/customers` | own | The caller's portfolio: customers they have a visit with, ∪ customers of quotes they wrote |
| GET | `/customers/{id}` | own | 404 whether absent or not theirs |
| GET | `/quotes` | current | Quotes the caller authored |
| POST | `/quotes` | current | Writes one, as a draft they own |
| POST | `/quotes/{id}/submit` | own | Sends it for validation |

| GET | `/account` | The caller's own **account**. Needs no assistant record |
| PATCH | `/account` | Display name and sign-in address. Nothing else exists on the payload |
| PUT | `/account/photo` | The caller's own portrait, as a **file**. Needs no assistant record |
| DELETE | `/account/photo` | Removes it. The screen falls back to the holder's initials |
| GET | `/company` | The caller's own agency. **Administrator only** |
| PUT | `/company` | Its name, SIRET, contact address, registered address and whether it accepts applications |

`/account` is guarded by `get_current_user` and nothing else, so every signed-in
caller can reach it — including a manager and an administrator. That is the
point of it: the account screen used to be built on `GET /me/hca`, which refuses
any account with no assistant record, so it rendered an error page to exactly
the people who could not fix it.

`/account/photo` is guarded the same way, and for the same reason. The portrait
belongs to the *credential*, so a manager and an administrator can set one —
`PUT /me/hca/photo` is bound to an assistant record and answers `403` for them,
which left them with no photograph at all rather than a locked one. When the
account **is** bound to a record, the service writes the same URL there too, in
the same transaction: an assistant's portrait is their pin on the manager's map,
and it is the same photograph of the same person.

It is uploaded as a file, never named as a URL. Accepting a URL would let
somebody point their avatar at any address on the internet, which every screen
showing them would then load — and the model refuses any value that does not
carry the object store's own key prefix, so a hand-written request cannot store
one either.

`AccountUpdateRequest` carries a display name and an address and **no other
field**. Role, active flag, agency, assistant binding and password hash are all
absent from the model rather than checked for, so a payload naming one is parsed
without it. A self-service account screen is precisely where somebody would try
to grant themselves a role, and there is no check to forget.

`/company` exists for the same reason `/account` does: an administrator signing
in has no way to know their agency's identifier, and a browser holding one it
read from somewhere else is how a screen edits the wrong tenant. The
agency-wide `PUT /api/v1/companies/{id}` still exists for the case where an
administrator genuinely means to name one.

Administrator, not manager. A manager runs the agency's work. Its legal identity
is not part of running the week, and the one field with an outward effect —
`is_accepting_applications` — decides whether strangers can apply for a job.

`/hca` and `/customers` need an account bound to an assistant record; `/quotes`
does not, because authorship is an account property and a manager who writes a
quote has as much claim to "my quotes".

`PUT /me/quotes/{id}/lines` is the self-service half of the manager route of the
same name. It is the **same service method**, called with the caller's identity:

```
QuoteService.replace_lines(quote_id, quote, author_id=None)   # manager: any quote
QuoteService.replace_lines(quote_id, quote, author_id=caller) # assistant: must be theirs
```

One method rather than two, because the two would each carry the draft-only
precondition and the repricing call, and that is two places for them to drift.
The author is compared against what is **stored on the quote**, never against
anything in the payload, so a hand-written request naming somebody else's quote
is answered `403` — which is what suite 20 asserts, since a hidden button proves
nothing.

## Quotes — `/api/v1/quotes` · all `manager`

| Method | Path | |
|---|---|---|
| POST | `` | Creates and prices. The author is the caller |
| GET | `` | `page`, `size`, `customer_id`, `status`, `authored_by`. **`status=pending-validation` is the validation queue** |
| GET | `/{id}` · `/{id}/aggregates` | One quote. Its weekly totals |
| PUT | `/{id}/lines` | Replaces the lines and reprices **any** quote in the agency. Drafts only |
| POST | `/{id}/price` | Reprices against the current catalog. Drafts only |
| POST | `/{id}/validate` | Approves a submitted quote → **`accepted`**, recording who. Its visits enter the next planning run |
| POST | `/{id}/refuse-validation` | Sends it back to its author → `draft` |
| POST | `/renewals/run` | Writes successors for expired auto-renewing arrangements. **Safe to repeat** |
| POST | `/{id}/interrupt` | Ends an arrangement on a day (inclusive) and reprices it |
| PATCH | `/{id}/auto-renew` | Turns renewal on or off |
| POST | `/{id}/send` | Issues a draft to the customer |
| POST | `/{id}/accept` · `/{id}/reject` | Records the **customer's** answer |

→ [04 — Quote lifecycle](04-quote-lifecycle.md) for why `validate` and `accept`
are different things.

## Catalogue pricing — `/api/v1/intervention-types` · all `manager`

| Method | Path | |
|---|---|---|
| GET | `/pricing-rules` | The agency-wide default rate, the weekday and holiday surcharges, and the VAT rate each service category carries |

Read-only, and read from the running configuration rather than the database: a
change to what *every* service costs is a commercial decision with a release
behind it. What an individual entry charges is editable, through
`PATCH /{id}`, and an entry that names no rate of its own bills at the agency
default.

**Declared before `/{type_id}`.** Routes match in registration order, so with
the parameterised route first this path would be read as a request for the
intervention type whose identifier is `"pricing-rules"` — a 404 naming a type
nobody asked for.

Every quote line must carry a `service_category` (`necessity` or `comfort`).
It is what the line's VAT is computed from, and it has no default — a payload
omitting it is answered 422 rather than quietly taxed at one of the two rates.
The catalogue entry named by `intervention_type_id` still fixes the hourly rate.

## Certifications — `/api/v1/certifications`

| Method | Path | Guard | |
|---|---|---|---|
| GET | `` | current | The catalogue, ordered by label. `include_inactive` shows retired entries |
| POST | `` | manager | Adds one. 409 if the code is taken |
| PATCH | `/{id}` | manager | Label, description and `is_active`. **Carries no `code`** |
| DELETE | `/{id}` | manager | 409 while anything refers to it, naming both counts |

**Readable by any signed-in caller**, unlike the writes. An assistant's own
account screen names the qualifications they hold, and a screen that could not
read this would have to print `DEAES` at somebody and hope.

**`code` is absent from the edit payload**, so no request can rename it. It is
what every stored qualification and every service requirement is matched on;
renaming it would leave a workforce holding certifications for a code that no
longer exists and disqualify all of them on the next planning run. The screen
locks the input, but a locked input is a courtesy — the absent field is the
control.

The delete refusal is the referential integrity the database cannot provide.
The references live in a JSON array and in a nullable column with no constraint
on either, so nothing at that level would stop a delete leaving a requirement
pointing at nothing. The 409 names how many assistants hold the code and how
many services require it, and says to retire the entry instead — "cannot
delete" with no reason is a message somebody works around by deleting the
assistant's qualification.

A requirement naming an unknown or retired code is a **422** wherever it is
written — on a catalogue entry or on a quote line — naming the offending code
and listing what the catalogue does offer. 422 and not 404: the resource being
addressed is the service or the line, and that one is there.

## Skills — `/api/v1/skills`

| Method | Path | Guard | |
|---|---|---|---|
| GET | `` | current | The catalogue, ordered by label. `include_inactive` shows retired entries |
| POST | `` | manager | Adds one. 409 if the code is taken |
| PATCH | `/{id}` | manager | Label, description and `is_active`. **Carries no `code`** |
| DELETE | `/{id}` | manager | 409 while anything refers to it, naming both counts |

Character for character the certification catalogue above, with the same
locked code, the same 409 offering retirement, and the same 422 for a
requirement naming an unknown code.

**The read matters more here.** An assistant declares their own skills from
their own account screen, so this is the list they pick from — a screen that
could not read it would leave them typing a code from memory and matching
nothing. The *catalogue* stays a manager's: a workforce able to invent entries
would produce a list nobody could require anything from.

### Declaring one — the asymmetry with certifications

| | Add | Remove |
|---|---|---|
| Certification | `PATCH /hcas/{id}/employment`, manager, whole list | same call, by omission |
| Skill | `POST /me/hca/skills`, **the owner only** | `DELETE /me/hca/skills/{id}` (owner) or `DELETE /hcas/{id}/skills/{id}` (manager) |

There is **no route by which a manager declares a skill for somebody else**,
and that is a routing decision rather than an oversight. A skill is a claim
about what somebody can do. A supervisor may withdraw one they believe is
wrong, but nothing lets them put a claim in another person's mouth.

`POST /me/hca/skills` takes an owner from the credential and mints the
identifier itself, so the payload carries neither — the two absences are the
permission. It answers **201** and publishes `skill.added`, which is what turns
into a notification for every manager and administrator of the agency. The
publish happens **after** the write, in the route rather than the service: a
message sent from inside would fire on a write a later failure could roll back,
and tell three managers about a skill nobody holds.

A withdrawal announces nothing. An addition widens what somebody may be sent
to. A removal only narrows it, and a badge for every correction of a typed name
would train supervisors to ignore the ones that matter.

## Notifications — `/api/v1/notifications`

| Method | Path | Guard | |
|---|---|---|---|
| GET | `` | current | The caller's own, newest first. No parameter names a recipient |
| GET | `/unread-count` | current | `{"unread": n}` — the badge |
| POST | `/{id}/read` · `/read-all` | current | Marks read |
| GET | `/stream` | *stream token* | Server-Sent Events |

The stream authenticates itself with a short-lived token in the query string,
because `EventSource` cannot set a header. It is exempt from the bearer
middleware and refuses a session token. → [11](11-security.md)

## People and workforce

**Customers** — `/api/v1/customers`, all `manager`: full CRUD, plus
`PATCH /{id}/status`, `POST /{id}/promote` and `GET /{id}/quotes`. `DELETE`
answers **202** with the replan it queued, or **204** when the customer had no
future visit — and it takes **every quote written for them** with it. Erasing
commercial history is irreversible, so the screen counts the quotes before it
asks; stopping the customer remains the reversible answer for one who was
really served.

`POST /{id}/promote` takes **no payload** — there is exactly one status a
promotion leads to, so a body carrying it would only be a way to ask for a
different one. It answers **409** for anybody who is not a `prospect`, rather
than succeeding silently: a control that does nothing on the second press is one
somebody presses twice and then wonders about. A named route rather than one
value among three on `PATCH /{id}/status`, so the rule lives in one place and
the log line says *promoted*.

`GET /customers` takes eight optional filters, bound as one `CustomerFilter`
model: `search`, `status`, `city`, `postal_code`, `email`, `phone`,
`has_ongoing_arrangement`, `is_geocoded`. An absent field narrows nothing. A
blank string is the same as absent. A status the system has no word for is
**422** rather than an empty page, because an empty page is what a valid filter
matching nobody looks like.

The flags are three-state — `true`, `false`, or absent. `is_geocoded=false` is a
question worth asking: those are the customers no planning run can ever route
to. `has_ongoing_arrangement` is defined **server-side** as an accepted quote
that has not been interrupted on or before today. Note this is narrower than the
drawer's client-side "live" set, which also counts `sent` and
`pending-validation` because it answers "what is in flight" rather than "who are
we serving".

The filter model is bound with `Depends()`, not `Annotated[..., Query()]`. Only
the former flattens it into individual query parameters. The latter binds it as
one parameter taking a JSON object, which 422s every request the screen sends.

**Assistants** — `/api/v1/hcas`, all `manager`: `POST`, `GET` (with `search`,
`contract_type`), `GET /{id}`, `DELETE`, and
`PATCH /{id}/employment` — the **only** manager-reachable mutation, carrying
contract type, certifications and `field_employee`.

`DELETE` answers **202** with the replan it queued, or **204** when they had no
future visit, and it removes the **sign-in account bound to them** in the same
transaction. An account whose `hca_id` names nothing cannot pass the row-level
planning check and cannot be repaired from any screen, so it cannot be left
behind — which is what the `RESTRICT` foreign key used to enforce by refusing
the whole deletion. `AuthService`'s own refusals still apply: never the
caller's own account, never the last administrator, both 409.

**The shape of `EmploymentUpdateRequest` is the permission.** A manager may
change three things about an assistant and nothing else, for anybody including
themselves. An assistant reaches no route that carries any of the three. That
rule lives in the payload rather than in a check somewhere that could be
forgotten.

**Photographs** — `PUT`/`DELETE /api/v1/hcas/{id}/photo` (multipart), and
`GET /api/v1/hcas/photo-constraints`. The content type is detected from magic
bytes, never the header; JPEG, PNG and WebP only; 5 MiB. Served straight from
the bucket, which is why the compose stack sets a public read policy.

**Availability** — `/api/v1/hcas/{id}/availability`, guard `current` with a
row-level ownership check, so an assistant files their own absences and a
manager files anybody's.

**Language** — carried on `PATCH /api/v1/me/account` alongside the display
name and the sign-in address, and published on every `UserResponse`. It is
the account holder's own preference, which is why it sits on that
self-service payload and not on a manager-gated one. An unknown code is a
422 rather than a silent fallback. → [04](04-quote-lifecycle.md)

**Working days** — `PUT /api/v1/hcas/{id}/working-days`, the same guard and
the same ownership check. This is the *recurring* pattern — "never
Wednesdays" — as opposed to the dated absences above. The two are separate
because only one of them ends when somebody comes back from leave. The
payload carries the whole week and no assistant identifier: the owner is
the one the path addresses, so there is nothing for a caller to put a
colleague's identifier into. A week naming no day is a 422 — clearing every
box is a statement, and its two readings are opposites. Answers the whole
`HcaResponse`, so a client need not re-read to redisplay.

**Applications** — `/api/v1/hca-applications`. `POST` is public. The queue and
the approve/reject decisions are `manager`.

## Planning — `/api/v1/planning`

| Method | Path | Guard | |
|---|---|---|---|
| POST | `/runs` | manager | **202, and a *list*.** One run per team, over one of three scopes: `?team_id=` plans that team, `?agency_id=` plans every team of that site the caller runs, naming neither plans the whole company and is **administrator-only**. Records each run before publishing it |
| GET | `/runs` · `/runs/{id}` | manager | Poll until `status.is_terminal()`. Narrowed to the caller's teams — this is what the screen polls, so leaving it at administrator made a manager's button look like it did nothing |
| GET | `/settings` · PUT | manager | Radius, working day, lunch break and its window |
| GET | `/hcas` | current | Every diary. An assistant gets a one-element list of their own |
| GET | `/hcas/{id}` | current | One diary, with a row-level ownership check |
| GET | `/customers` | current | Every household's care. A manager gets the agency. An assistant only their own portfolio |
| GET | `/customers/{id}` | current | One household's care. Outside an assistant's portfolio it is a **404**, not a 403 |

`POST /runs` moved from administrator to manager because a run no longer
rewrites every calendar in the agency — it rewrites one team's. Which team a
caller may name is checked in the service against the credential, because a
route guard can only prove a rank: nothing at the routing layer stops manager A
naming manager B's team.

**Three scopes, narrowest first: a team, a site, the company.** A team is what a
manager owns and a site is the level above it, so both are theirs — but the site
case *intersects* with the teams they run rather than taking the site's roster
wholesale, or a branch office would be a way to rebuild a colleague's week
without ever naming their team. Naming no scope at all means the whole company,
and that is an administrator's act: it rewrites the calendar of every assistant
employed, and no manager is answerable for all of them. A manager who names
nothing is **refused with a 403** rather than quietly given their own teams —
being told the company had been re-planned when one team was would be worse than
the refusal.

Both run reads are narrowed by `readable_team_ids` as well, and for a reason
that is not only confidentiality: starting a run hands the caller its
identifier, so every manager holds real ones and could otherwise poll a
colleague's to learn how much of that team's week would not fit.

The two `/customers` routes read through the same repository method the
household's own `/api/v1/portal/planning` reads through, with the same
arguments and no filter of either side's own — so the agency and the family
cannot be shown different weeks. A household reaching either is a **403**: the
staff test comes before anything that ranks, because ranking a customer raises
and would surface as a 422 about role ladders.

If the broker is unreachable the run stays `pending` rather than vanishing — the
identifier the caller polls is real either way.

`DELETE /api/v1/planning/interventions/{id}` answers 202 the same way, taking
the period from the caller's own screen. The two person deletions derive theirs
from the days that person was due to work. All four record the run before
publishing it, so a 202 always hands back an identifier that already exists.

## The organisation — `/api/v1/agencies` and `/api/v1/teams`

| Method | Path | Guard | |
|---|---|---|---|
| POST | `/agencies` | admin | **The type is overwritten.** The first site of a company is its head office; every later one is a branch, and a second head office is a **409** |
| GET | `/agencies` · `/agencies/{id}` | current | Open to every signed-in account, and safe because the projection publishes no legal identity — see below |
| PUT | `/agencies/{id}` | admin | Name, address and type. The head office cannot be demoted, nor a branch promoted |
| DELETE | `/agencies/{id}` | admin | **409** while any team or person is still attached, naming both counts |
| GET | `/agencies/{id}/members` | current | Pairs of *(kind, identifier)*, and nothing else |
| POST | `/agencies/{id}/members` | admin | **A transfer.** Somebody already at another site is moved off it, and off a team based there; **409** only if they run that team |
| DELETE | `/agencies/{id}/members/{kind}/{id}` | admin | The kind is a path segment because it is half of the identity |
| POST | `/teams` | admin | Enrols the named manager as a member in the same call |
| GET | `/teams` · `/teams/{id}` | current | Narrowed: the company for an administrator, their own for a manager, one for an assistant |
| PUT | `/teams/{id}` | admin | Name, site and manager. Members do not follow a move |
| DELETE | `/teams/{id}` | admin | **409** while quotes still name it — they would be planned by no run again |
| GET · POST | `/teams/{id}/members` | current · admin | One person at a time, and a **move**: somebody on another team is taken off it. **409** only if they run that team; **422** if they are based at another site |
| DELETE | `/teams/{id}/members/{kind}/{id}` | admin | The manager cannot be removed. Name a new one instead |
| GET · POST | `/teams/{id}/documents` | current | **Everybody on the team may add one.** A non-member gets a 404 |
| GET | `/teams/{id}/documents/{doc}` | current | Streamed as an attachment, with the stored media type |
| DELETE | `/teams/{id}/documents/{doc}` | current | The uploader, the team's manager or an administrator. Anybody else gets a **403** |
| GET | `/teams/document-constraints` | current | The size limit and the recognised media types |
| GET | `/me/team` | current | The team the caller is *on*, from the credential |
| PATCH | `/quotes/{id}/team` | manager | Move a quote. Both the team it leaves and the one it joins must be the caller's |

**An `Agency` is a `Company`.** The stored record carries the SIRET, the VAT
number and the account invoices are paid into, because the head office is where
the business is registered and a quote is printed from the site it was written
at. None of that is published by these routes: the response model declares the
name, the address, the type and two counts. That is what makes the reads safe to
open to an assistant, and a test asserts the field set is disjoint from the
legal-identity fields — the risk being a field *added* later.

`/teams/document-constraints` is declared **before** `/teams/{id}` in the mount
order, or FastAPI would read `document-constraints` as a team identifier.

## Billing — `/api/v1/bills` and `/api/v1/billing`

Three routers, all under `api/v1/bills/`, all `manager`.

| Method | Path | |
|---|---|---|
| POST | `/bills/runs` | **202.** Records the run, publishes it, returns the identifier to poll |
| GET | `/bills/runs` · `/bills/runs/{id}` | Poll until `status.is_terminal()` — which includes `partial` |
| GET | `/bills` | The invoice book, narrowed by `search`, `number`, `customer_id`, `status`, `is_sent`, `period_start`, `period_end` |
| GET | `/bills/{id}` | One invoice, with its lines |
| PATCH | `/bills/{id}/status` | Move it along the `BillStatus` chain |
| GET | `/bills/{id}/document` | The PDF, as `application/pdf` |
| POST | `/bills/customers/{customer_id}?reference_date=` | Bill one customer for the period containing that day |
| GET | `/billing/settings` · PUT | The agency's invoicing rules |

**Two prefixes, one folder.** `api/v1/billing/` and `api/v1/bills/` were merged
into `api/v1/bills/`, but the settings routes keep `/api/v1/billing/settings`
and that is deliberate: `/api/v1/bills/settings` has the same shape as
`/api/v1/bills/{bill_id}`, so mounting order would decide whether asking for the
rules looked up a bill numbered "settings". They are the agency's invoicing
*rules* rather than one of its bills, and the URL says so.

**Mounting order is load-bearing** for the same reason. `main.py` includes the
run router **before** the bill router, because `/bills/runs` and
`/bills/{bill_id}` also collide — reversed, the run list would 404 as a missing
bill named "runs".

A run answers **202** and can finish `partial`: some customers billed, some in
`failed_customer_ids`. Unlike a planning run, that is a success worth keeping —
see [02](02-domain-model.md#billing).

## The customer portal — `/api/v1/portal` · all `customer`

The household's own space. **Every route resolves the household from the
credential and never from a path parameter**, so there is no identifier a
customer could point at somebody else's file.

| Method | Path | |
|---|---|---|
| GET | `/profile` · PUT | Their own record. The payload carries the contact block and **nothing else** — no status, no billing periodicity |
| GET | `/planning?period_start=&period_end=` | Their visits. The period is required: an unbounded read would return every visit ever to draw one week |
| POST | `/interventions/{id}/cancel` | Cancel a visit |
| POST | `/interventions/{id}/reschedule` | Move one to a day and a **window** |
| GET | `/quotes` · `/quotes/{id}/document` | Their quotes, unfiltered, and the PDF |
| GET | `/bills` · `/bills/{id}/document` | Their invoices, and the PDF |

**Both write routes send the quote back to `pending-validation`** and queue a
replan. That is the whole difference between a household changing their work and
a manager doing it: `QuoteService.reschedule_line` deliberately leaves the status
alone, because a manager answers *when*, while a household changes what the
agency agreed to deliver. Until it is re-validated, **nothing on that quote is
scheduled** — not only the visit that changed.

The replan is the consequential part. Without it the cancelled or moved visit
sits on an assistant's calendar until somebody starts a run by hand, and an
assistant is sent to a door for work the household withdrew.

A visit, quote or invoice belonging to another household answers **404, not
403** — the same rule the assistant portfolio follows. Distinguishing the two
would let somebody walk the identifier space and learn when the agency visits
their neighbours.

Staff are refused every route here, and a household is refused every staff
route. The guard compares by **identity**: a customer is not a rung of the staff
ladder, and `has_at_least` raises rather than answering.
→ [11](11-security.md#the-customer-is-not-a-rung-of-the-ladder)

`GET /api/v1/quotes/{id}/document` is the manager's twin of the portal
download, written in the caller's language rather than the household's. Both
render **on demand and store nothing**: unlike an invoice, a quote is still an
offer that gets re-priced and edited, so a stored file would serve last month's
prices. An unpriced quote answers **422** rather than printing a blank amount,
which would read as *free*.

`POST /api/v1/customers/{id}/account` (manager) is how a household gets access:
it answers **201** with a one-time password, returned once and never stored in
plaintext or emailed — the same trade staff accounts make. A second invitation
for the same household answers **409**.

## Other

`GET /health`, `GET /ready` — unauthenticated probes.
`GET /api/v1/companies/choices` — public, so an applicant can pick an agency.
`POST /api/v1/companies/registration` — public, and **off unless the
deployment opts in**. Founds an agency and makes its author the
administrator; see [Founding an agency](#founding-an-agency).
`/api/v1/users` — administrator only. `DELETE /api/v1/users/{id}` removes an
account outright and refuses the caller's own and the last administrator;
**deactivating is the ordinary way** to stop somebody signing in, since
removing a person who worked here erases who validated what.
`DELETE /api/v1/companies/{id}` removes an agency, and answers 409 while any
account or assistant still belongs to it — the refusal names how many of
each. Both exist for records that should never have been: one raised in
error, and the fixtures the QA campaign removes after itself.
`POST /api/v1/webhooks/planning-completed` — shared secret in `X-Webhook-Token`.

## Two things a client author needs

**FastAPI publishes no `securitySchemes`.** Authentication lives in middleware
and the guards take a bare `Request`, so nothing in the schema says these routes
need a credential. `/docs` has no Authorize button, and a generated client
produces no auth handling. The front-end attaches the bearer header itself.

**Pydantic v2 splits models** into `X-Input` and `X-Output` variants for
`Customer`, `Quote` and `InterventionType`. The front-end's hand-written types
collapse that. The `openapi-drift` CI job is what stops them going stale.


## Founding an agency

`POST /api/v1/companies/registration` — unauthenticated. Creates a company and
an administrator account for it in one request, and answers **201** with both.

```json
{
  "company_name": "Aide et Presence Lyon",
  "registration_number": "812 345 678 00019",
  "full_name": "Camille Fournier",
  "email": "camille@aide-lyon.fr",
  "password": "a-founder-password-2026"
}
```

The registration number is optional: an agency being founded may not have been
issued one, and refusing to let it exist until it has would put the paperwork
before the product. No address is taken —
[`PostalAddress`](02-domain-model.md) geocodes during validation, and a required
address would put a live Nominatim lookup on the sign-up path where a slow third
party reads as a broken form. The founder fills it in afterwards.

**No token comes back.** Founding an agency and holding a session are separate
things. Issuing one here would be a second place that mints credentials, and so
a second place to get expiry, scope and revocation wrong. The founder signs in
through `POST /api/v1/auth/login` with the password they just chose.

| Answer | When |
|---|---|
| 201 | The agency and its administrator were created |
| 404 | The deployment has not opted in — see below |
| 409 | The company name or the email address is already taken |
| 422 | A field is missing, blank, or the password is outside 12–72 bytes |

**Off unless the deployment opts in.** `auth.allow_company_registration` is
`false` in `app.yaml` and `true` in `app.dev.yaml` and `app.docker.yaml`. A
deployment that has not opted in answers **404, not 403**: a 403 confirms the
feature exists and is merely switched off, which invites somebody to keep
checking whether it has been switched on. Why it is opt-in at all is a security
question → [11](11-security.md).
