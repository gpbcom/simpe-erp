# 11 — Security

## Authentication

Sign in at `POST /api/v1/auth/login`; get an HS256 JWT valid for 720 minutes.

The token carries **three claims only** — `sub` (the email address), `iat`,
`exp`. No role, no identifier, no company. `AuthMiddleware` re-reads the account
from the database on every request, so a demotion, a deactivation or a deletion
takes effect **at once** rather than when the token expires.

There is no refresh token. The client signs in again.

Every sign-in failure raises the same exception with the same message, whether
the address is unknown or the password is wrong — telling them apart would turn
the endpoint into an account-enumeration oracle. A deactivated account is the
one deliberate exception: the person needs to know to contact an administrator,
and they have already proved they hold the password.

## Where the checks live

**Authentication is middleware. Authorisation is a per-route guard. Row-level
ownership is in the service.**

That split is deliberate. A route added without a guard is still
*authenticated*, so forgetting one leaves the endpoint unauthorised rather than
open. And the row-level comparison can only be made where the stored record is —
a guard proves the caller is *an* assistant; nothing at the routing layer stops
assistant A putting assistant B's identifier in the path.

| Guard | Passes for |
|---|---|
| `get_current_user` | Any signed-in account |
| `get_hca_user` | Exactly `hca` — identity, not rank, so a manager fails it |
| `get_manager_user` | `has_at_least(MANAGER)` — an admin passes |
| `get_admin_user` | `is_admin()` |
| `get_customer_user` | Exactly `customer` — **and it cannot be written any other way**; see below |

Row-level checks, and what each stops:

| Check | Stops |
|---|---|
| `PlanningService.planning_for` | One assistant reading another's diary |
| `HcaService._check_owns` | Filing an absence against a colleague, taking them off the rota |
| `QuoteService.submit_for_validation` | Submitting somebody else's draft |
| `CustomerRepository.is_served_by` | Reading a customer outside your portfolio |
| `NotificationRepository.mark_read` | Reading somebody else's queue by guessing an identifier |
| `User.owns_customer` | One household reading another's file |

## The customer is not a rung of the ladder

`UserRole` looks like four values and is really **two axes**. `hca < manager <
admin` is a ladder and `has_at_least` walks it. `customer` is not above or below
any of them — it is somebody the agency serves rather than somebody who works
for it.

**`rank()` therefore refuses to rank a customer**, raising `MTRoleNotRankable`.
That refusal is the security control, not tidiness. There is no number that
works:

- ranked **below** `hca`, every employee satisfies `has_at_least(CUSTOMER)`, so
  a guard written the ordinary way admits all staff to a household's space;
- ranked **above** `admin`, a customer satisfies every manager check.

So `get_customer_user` compares by identity, `hasAtLeast` in the front-end is
never called with `'customer'`, and the portal routes sit behind a distinct
`CustomerRoute` rather than `RoleRoute minimum=`. A call that gets this wrong
raises instead of returning a plausible boolean — the failure mode of a
privilege check that quietly answers `True` is that nobody ever finds it.

`UserRole.is_staff()` is the one safe way to ask the other question. It is
written as a method so a fifth role added later cannot be admitted to the staff
side by not being mentioned — which is exactly how `owns_hca` broke:

> It read `if self.role is not UserRole.HCA: return True`, correct while the
> only other roles were manager and admin. The moment `customer` existed, that
> spelling handed every assistant's diary — with every household's name and
> address on it — to every customer. Nothing raised. The test named
> `test_a_customer_owns_nobodys_planning` is there so it cannot come back.

### The link runs both ways

`users.customer_id` is set for a customer account and **forbidden on every
other role**, enforced by `User.check_customer_link` at construction. The
reverse direction is the one that matters: a manager carrying a `customer_id`
would satisfy the staff guards *and* resolve to one household — an account on
both sides of the boundary at once. Refused at construction, the state cannot
exist for a service to reason about.

Portal routes resolve the household from `caller.customer_id` and **never from a
path parameter**, so there is no identifier a customer can point at somebody
else's file. `owns_customer` is the second gate behind that, for the route
somebody adds later without remembering the first.

## Scoping

An assistant sees the customers they have a planned visit with, **union** those
on quotes they wrote — not the agency's book. A home-care record carries an
address, a telephone number and a care schedule; there is no reason for every
assistant to hold every one of them.

The scoping is applied **in the SQL statement**, not by filtering rows
afterwards. A page of fifty narrowed to three has already read forty-seven
records the caller may not see.

A customer outside the portfolio answers **404, not 403** — and a notification
that is not yours answers 404 too. Distinguishing "does not exist" from "not
yours" lets a caller walk the identifier space and learn what the agency holds,
which is most of what a customer list is worth.

## What a payload cannot carry

Three fields are taken from the credential and never from the request body:

| Field | Route | If it came from the payload |
|---|---|---|
| `role` | `POST /auth/register` | Anybody could register themselves an administrator |
| `authored_by` | quote creation | A quote lands in somebody else's list, and they answer for a price they never set |
| the assistant record | every `/me/*` route | An assistant reads or edits a colleague's |
| `role` | `POST /companies/registration` | Same as above, through a newer door |
| `company_id` | `POST /companies/registration` | Founding an agency becomes taking over somebody else's |
| `company_id` | quote creation | A quote written into another agency, whose assistants are then sent out to deliver it |
| `status`, `validated_by` | quote creation | A caller accepts their own quote, in somebody else's name, without a manager ever seeing it |
| the lines alone | `PUT /quotes/{id}/lines` | A repricing that could also reassign the quote, or move it between agencies |

`RegisterRequest`, `CompanyRegistrationRequest`, `HcaProfileUpdateRequest`,
`QuoteCreateRequest` and `QuoteLinesRequest`
achieve this **structurally**:
the fields do not exist on the model. A field that is not there cannot be
honoured by an endpoint that forgets to ignore it, or re-added by a refactor
that stops excluding it.

`HcaProfileUpdateRequest` has no `certifications`, no `contract_type` and no
`field_employee` for that reason. An assistant who could grant themselves a
qualification could be routed to work they are not trained for; one who could
clear their own `field_employee` could take themselves off every round without
telling anybody, and the workforce would shrink with nothing on any screen
saying why.

**`SkillCreateRequest` is the one place that rule is deliberately inverted**,
and it is inverted the same way: structurally. It carries no `hca_id` and no
`id`, so the owning assistant comes from the credential and the identifier from
the store — a payload cannot file a declaration against a colleague or
overwrite an existing row by naming one. What it *does* let its sender do is
change who the planner may assign them to, which nothing else on the
self-service surface does.

That is a considered trade rather than a gap. A certification is a claim about
what somebody was **awarded**, so an assistant granting themselves one could be
routed to work they are not trained for. A skill is a claim about what they
**can do**, and an assistant who cannot say they speak Portuguese is one the
agency does not know it has. The safeguard is not a form in a queue — it is
that every manager and administrator is notified of every declaration, and any
of them can withdraw it through `DELETE /hcas/{id}/skills/{id}` before the next
planning run acts on it. There is deliberately no route by which a supervisor
*declares* one for somebody else.

All three live on the manager-gated `EmploymentUpdateRequest` instead, which a
manager or an administrator reaches **for anybody, including themselves** —
the route takes an identifier and they hold the role. That is deliberate: a
manager who covers rounds is ordinary, and needing a second person to record it
would be friction with no security behind it. What no assistant can reach is
the payload at all.

Suite 26 asserts this from both sides: the screen shows the flag as a locked
chip, and the request the form will not make is sent by hand against the
manager route *and* against the self-service one. A form that merely omits a
control is not the control.

### The two quote payloads

Both routes used to accept a whole `Quote` and read some of it. That made every
guarantee a matter of the service remembering not to look — and `PUT
/quotes/{id}/lines` said so in prose: "only the lines are taken from the body".

The prose was true and the type was not. `QuoteCreateRequest` carries a
reference, a customer and lines; `QuoteLinesRequest` carries lines. Neither can
name an agency, a status or a validator.

That stopped being cosmetic the moment a quote carried its agency. The agency
decides whose accepted work a planning run schedules and whose calendar it
rewrites, so a body wide enough to hold one was a way to have another agency's
assistants deliver work they had never agreed to.
→ [02](02-domain-model.md)

## Founding an agency

`POST /api/v1/companies/registration` is unauthenticated and grants its author
the **administrator** role. That is only defensible because of what the role is
over: the company is created by the same call, so there is nothing that existed
a moment ago to take control of. There is no `company_id` field, and adding one
would turn founding an agency into a takeover.

**It is off unless the deployment opts in**, and that default is the point.
A company is not yet a tenancy boundary here — see [Scoping](#scoping): customers,
quotes, plannings and assistants are global, and `get_admin_user` checks the role
without looking at the company. An administrator minted by public sign-up
therefore reads **every** agency's records, not only the one they just founded.
Until the company scoping exists, `auth.allow_company_registration` keeps that
from being the posture a deployment gets simply by standing the service up. It is
`true` in the development and demonstration configurations, which hold seeded
records rather than real ones, and `false` in `app.yaml`.

The flag refuses a *string*. YAML already turns `no`, `off` and `false` into
booleans, but a quoted `"false"` is a non-empty string and would otherwise read
as **true** — opening the route on a deployment whose configuration says, in
plain sight, that it is closed.

The middleware exemption is an **exact path**, not a prefix. Listing agencies,
reading one, editing one and opening or closing its applications all live under
`/api/v1/companies` and all stay behind a gate.

## Everybody belongs to an agency

`company_id` is required on every account and every assistant, and `NOT NULL` in
both tables. The agency is derived — from the assistant record for a
self-registered or staff-created account, from the agency created by the same
call when one is founded — and never taken from a payload. → [02](02-domain-model.md)

Closing that removed a real hole rather than tidying a type. An administrator
belonging to **no** agency was treated as system-wide when deciding
applications, so any such account could decide every agency's queue. The
exemption is gone, not left as unreachable code: one that cannot currently be
reached is one a later change can quietly make reachable again.

It also gives the broker something to route on — see
[05](05-events-and-notifications.md). Each agency has its own queues, so one
agency's backlog, poison message or dead-letter queue is its own. That is
isolation of *delivery*, not yet of *visibility*: the scoping gap below is
still open.

## Credentials

bcrypt, with a dummy hash compared when the address is unknown so the timing
does not distinguish the two cases. Passwords are 12–72 characters — the upper
bound is not arbitrary: bcrypt silently ignores anything past 72 bytes, so a
longer password would appear accepted while only its first 72 bytes mattered.
Measured in **bytes**, so an accented password reaches the limit sooner.

A rejected password never appears in a response or a log.

An account created by staff gets a one-time password returned **once**, and
`must_change_password` set. The middleware then answers **403 on every route but
the password change** until it is cleared — checked at the middleware so a route
added tomorrow is covered too.

## The stream token

`EventSource` cannot set an `Authorization` header, so the SSE stream has to
authenticate through the URL — and a URL reaches referrer headers, proxy logs
and browser history.

So `POST /api/v1/auth/stream-token` mints a **60-second token scoped
`stream`**. `read_subject` refuses it everywhere else and `resolve_stream_token`
refuses a session token: the scope is checked in both directions, because a
credential that works in two places is two places it can leak from.

The stream path is exempt from the bearer middleware and validates that token
itself.

## Transport and headers

CORS names its origins explicitly rather than `*`, because the API answers
credentialed requests and a wildcard would let any site drive it with a signed-in
user's token. It is the **outermost** middleware, so a 401 still carries the CORS
headers — otherwise the browser reports an opaque network error instead of the
answer it was given.

In production nginx proxies `/api`, so the browser is same-origin and CORS stops
being load-bearing.

## Uploads

Content type is detected from **magic bytes**, never the `Content-Type` header.
JPEG, PNG and WebP only, 5 MiB, with the key freshly generated per upload so a
CDN never serves a stale portrait. The account's own portrait
(`PUT /api/v1/me/account/photo`) goes through the same store and the same
checks; those are the only upload endpoints in the API.

## Three endpoints that answer without a credential

`/health`, `/ready` and `/metrics` are exempt from the bearer-token middleware,
because a kubelet and a scraper have no account to sign in with.

What makes `/metrics` defensible is what it carries: counts and durations, with
every label drawn from an enum. **No label identifies a person** — no `hca_id`,
no `customer_id`, no `company_id` — which is a property `ApplicationMetrics` is
responsible for and has a test for. It is also absent from the OpenAPI document,
and the ingress does not route it: it is served for a scraper inside the
cluster. → [14](14-observability.md)

## Secrets in the cluster

The `*_env` pattern is unchanged — a YAML key names an environment variable, the
value is read at connection time, and no password is ever written into a
configuration file.

What changes is where the variable comes from. In compose it is `.env`; in the
cluster it is a Secret written by **External Secrets** from the cluster's own
store, which the chart declares as an `ExternalSecret` and never as a value.
Rotating one is a change in that store and a pod restart — never a rebuild, and
never a value in git.

**PgBouncer sits between the application and PostgreSQL**, which is a connection
change rather than a security one, but worth knowing when reading a connection
log: the backend PostgreSQL sees is the pooler's, not the pod's.
→ [13](13-kubernetes.md)

## Known gaps

Stated rather than hidden.

1. **The photograph bucket is publicly readable.** `photo_url` is an absolute
   URL and there is no proxy or presigned-URL support, so `<img src>` requires
   it. Anybody with a URL can fetch a portrait. Fixing it means a download
   endpoint or presigned URLs.
2. **`HcaApplication` responses include `hashed_password`** — a bcrypt hash sent
   to the client. It should not be on the response model.
3. **No rate limiting** anywhere, including on login.
4. **No refresh token**, so a 12-hour access token is the whole session. Shorter
   would mean signing in during the working day.
5. **No audit log** beyond the per-record `updated_by` / `validated_by` columns.
6. **`ty` is not yet a blocking gate** → [10](10-testing.md).
7. **A company is not a tenancy boundary.** Only `users` and
   `hca_applications` filter by `company_id`; customers, quotes, plannings,
   assistants and the catalogue are global, and the administrator gate does
   not look at the company. This is why public company registration is
   opt-in rather than on — see [Founding an agency](#founding-an-agency).
   Closing the gap means scoping every query and making `get_admin_user`
   company-aware.

## Fixed in this codebase, worth not reintroducing

- `POST /auth/register` accepted an arbitrary `role`. An unauthenticated caller
  could register themselves an administrator. The field is **deleted**, not
  defaulted.
- `AuthMiddleware.EXEMPT_PATHS` exempted the `/api/v1/hca-applications`
  **prefix**, so the manager-only queue and decision routes bypassed
  authentication entirely — and, because `request.state.user` was never set,
  always answered 401. Now only `POST` on the exact path is public.
- `S3Storage.ensure_bucket()` existed and was never called, so uploads failed
  against a fresh object store. It runs at start-up.
