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

`/hca` and `/customers` need an account bound to an assistant record; `/quotes`
does not, because authorship is an account property and a manager who writes a
quote has as much claim to "my quotes".

## Quotes — `/api/v1/quotes` · all `manager`

| Method | Path | |
|---|---|---|
| POST | `` | Creates and prices; the author is the caller |
| GET | `` | `page`, `size`, `customer_id`, `status`, `authored_by`. **`status=pending-validation` is the validation queue** |
| GET | `/{id}` · `/{id}/aggregates` | One quote; its weekly totals |
| PUT | `/{id}/lines` | Replaces the lines and reprices. Drafts only |
| POST | `/{id}/price` | Reprices against the current catalog. Drafts only |
| POST | `/{id}/validate` | Approves a submitted quote → `sent`, recording who |
| POST | `/{id}/refuse-validation` | Sends it back to its author → `draft` |
| POST | `/{id}/send` | Issues a draft to the customer |
| POST | `/{id}/accept` · `/{id}/reject` | Records the **customer's** answer |

→ [04 — Quote lifecycle](04-quote-lifecycle.md) for why `validate` and `accept`
are different things.

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
`/api/v1/users` — administrator only.
`POST /api/v1/webhooks/planning-completed` — shared secret in `X-Webhook-Token`.

## Two things a client author needs

**FastAPI publishes no `securitySchemes`.** Authentication lives in middleware
and the guards take a bare `Request`, so nothing in the schema says these routes
need a credential. `/docs` has no Authorize button, and a generated client
produces no auth handling. The front-end attaches the bearer header itself.

**Pydantic v2 splits models** into `X-Input` and `X-Output` variants for
`Customer`, `Quote` and `InterventionType`. The front-end's hand-written types
collapse that; the `openapi-drift` CI job is what stops them going stale.
