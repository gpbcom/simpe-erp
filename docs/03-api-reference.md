# 03 — API reference

**58 paths, 76 operations.** The live schema is at `/openapi.json`, rendered at
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
credential; no path parameter names it.

| Method | Path | Guard | |
|---|---|---|---|
| GET | `/hca` | own | The caller's own assistant record |
| PATCH | `/hca` | own | Contact details and address. **No `contract_type`, no `certifications`** — the payload has no such fields |
| GET | `/customers` | own | The caller's portfolio: customers they have a visit with, ∪ customers of quotes they wrote |
| GET | `/customers/{id}` | own | 404 whether absent or not theirs |
| GET | `/quotes` | current | Quotes the caller authored |
| POST | `/quotes` | current | Writes one, as a draft they own |
| POST | `/quotes/{id}/submit` | own | Sends it for validation |

| GET | `/account` | The caller's own **account**. Needs no assistant record |
| PATCH | `/account` | Display name and sign-in address. Nothing else exists on the payload |
| GET | `/company` | The caller's own agency. **Administrator only** |
| PUT | `/company` | Its name, SIRET, contact address, registered address and whether it accepts applications |

`/account` is guarded by `get_current_user` and nothing else, so every signed-in
caller can reach it — including a manager and an administrator. That is the
point of it: the account screen used to be built on `GET /me/hca`, which refuses
any account with no assistant record, so it rendered an error page to exactly
the people who could not fix it.

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

Administrator, not manager. A manager runs the agency's work; its legal identity
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
| POST | `` | Creates and prices; the author is the caller |
| GET | `` | `page`, `size`, `customer_id`, `status`, `authored_by`. **`status=pending-validation` is the validation queue** |
| GET | `/{id}` · `/{id}/aggregates` | One quote; its weekly totals |
| PUT | `/{id}/lines` | Replaces the lines and reprices **any** quote in the agency. Drafts only |
| POST | `/{id}/price` | Reprices against the current catalog. Drafts only |
| POST | `/{id}/validate` | Approves a submitted quote → `sent`, recording who |
| POST | `/{id}/refuse-validation` | Sends it back to its author → `draft` |
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
`PATCH /{id}/status` and `GET /{id}/quotes`. Deleting a quoted customer is a
409: erasing commercial history is a deliberate decision, not a side effect.

**Assistants** — `/api/v1/hcas`, all `manager`: `POST`, `GET` (with `search`,
`contract_type`), `GET /{id}`, `DELETE`, and
`PATCH /{id}/employment` — the **only** manager-reachable mutation, carrying
contract type and certifications.

**Photographs** — `PUT`/`DELETE /api/v1/hcas/{id}/photo` (multipart), and
`GET /api/v1/hcas/photo-constraints`. The content type is detected from magic
bytes, never the header; JPEG, PNG and WebP only; 5 MiB. Served straight from
the bucket, which is why the compose stack sets a public read policy.

**Availability** — `/api/v1/hcas/{id}/availability`, guard `current` with a
row-level ownership check, so an assistant files their own absences and a
manager files anybody's.

**Applications** — `/api/v1/hca-applications`. `POST` is public; the queue and
the approve/reject decisions are `manager`.

## Planning — `/api/v1/planning`

| Method | Path | Guard | |
|---|---|---|---|
| POST | `/runs` | admin | **202.** Records the run, publishes it, returns the identifier to poll |
| GET | `/runs` · `/runs/{id}` | admin | Poll until `status.is_terminal()` |
| GET | `/settings` · PUT | manager | Radius and lunch break |
| GET | `/hcas` | current | Every diary. An assistant gets a one-element list of their own |
| GET | `/hcas/{id}` | current | One diary, with a row-level ownership check |

If the broker is unreachable the run stays `pending` rather than vanishing — the
identifier the caller polls is real either way.

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
collapse that; the `openapi-drift` CI job is what stops them going stale.


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
things; issuing one here would be a second place that mints credentials, and so
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
