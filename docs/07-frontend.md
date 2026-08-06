# 07 — Front-end

React 19 + TypeScript (strict) + MUI v6, built by Vite. `frontend/`.

## Stack, and why

| Concern | Choice | Because |
|---|---|---|
| UI | MUI v6 + MUI X DataGrid, date pickers | An ERP needs dense tables, date ranges and a consistent dark theme on day one |
| Server state | TanStack Query v5 | Caching, invalidation and loading states belong to one layer |
| Client state | Zustand — **the session only** | Everything else on screen is server state; duplicating it is how two components disagree about the same quote |
| Routing | React Router v7 | — |
| Forms | React Hook Form + Zod | — |
| i18n | react-i18next, **French default** | The domain is French: CDI/CDD, +33 numbers, EUR, French holidays |
| Calendar | FullCalendar | The planning is a diary, not a list |
| Map | react-leaflet + OpenStreetMap | No API key, no billing, and it matches the Nominatim geocoding already in use |
| Tests | Vitest + Testing Library; Robot Framework for the GUI | — |

## Screens

```
/login                       (rendered when there is no session)
/change-password             (rendered when must_change_password is set)

  assistant                          manager / administrator
  ─────────────────────────          ──────────────────────────
  /me            account             /quotes    every quote + validation queue
  /me/planning   calendar            /hcas      workforce + qualifications
  /me/customers  portfolio           /map       intervention map
  /me/quotes     own quotes          /notifications
```

`/` redirects to `/quotes` for a manager and `/me/planning` for an assistant.
An unknown route falls back to the same place.

### The four that carry the requirements

**`/me` — the account page.** Contact details and address are editable. Contract
type and qualifications render as **locked chips with a tooltip naming who owns
them**, not as disabled inputs: a disabled input says "you cannot type here", a
locked chip says who to ask. The request model has no such fields at all, so
they cannot be smuggled in.

**`/me/planning` — the calendar.** FullCalendar `timeGridWeek`, bounded to
07:00–21:00 and five columns. Two permanently empty weekend columns waste width
on a laptop, and bounding the day is what makes an empty morning *visibly*
empty rather than scrolled off the top. Clicking a visit opens a drawer with the
address the assistant travels to.

**`/quotes` — the validation queue.** Six tabs, opening on
`pending-validation`. Validate and Refuse render **only on a submitted quote** —
disabled buttons on all ninety rows would bury the six that are waiting, which
is the whole point of the screen.

**`/map` — the intervention map.** One pin per intervention over a configurable
window. The pin is a Leaflet `divIcon` carrying the **assistant's photograph**,
ringed in the intervention's status colour, falling back to their initials —
"who is where" is the question, and a blank circle does not answer it. The
tooltip names the customer, their address and telephone number, the service and
the time. A side list mirrors the pins, and a counter reports drawn against
total, because a silently dropped pin is a visit nobody is looking at.

## API layer

`src/api/types.ts` is **hand-written**, which is a deliberate trade. FastAPI
publishes no `securitySchemes` and Pydantic v2 splits every model into
`Input`/`Output` variants, so a generated client produces two types per entity
and no auth handling. The `openapi-drift` CI job regenerates the schema and
fails on a mismatch, so hand-written does not mean allowed to drift.

`src/api/client.ts` attaches the bearer header, and distinguishes three answers:

- **401** — clear the token and drop the session. A credential the server has
  stopped accepting is worse than none: every screen would fail with a different
  symptom instead of one clear sign-in page.
- **403 with `must_change_password`** — a state to navigate on, not an error to
  apologise for.
- anything else — an `ApiError` carrying the status and `detail`.

`openNotificationStream` fetches a fresh 60-second stream token, opens the
`EventSource`, and on error closes and reconnects with a **new** token —
`EventSource`'s own retry would replay the dead one forever.

`src/api/queries.ts` holds every query key in one factory. Two components that
spell a key differently produce a screen that does not refresh, and no error
anywhere.

## Branding

Hand-authored SVG, no binary assets and no icon font — a font is one more
request that can fail, and cannot inherit `currentColor` per path.

- **Mark** — a roof over a heart formed from two hands: care delivered at home.
  Drawn on a 48-unit grid with 3.5-unit strokes so it survives at 16 px.
- **Icons** — `src/components/icons/AppIcon.tsx`, fifteen glyphs on one 24×24
  grid with a 1.75 stroke, reached through a single facade so the set stays
  consistent. Stroked, matching MUI's outlined variants: a filled glyph beside an
  outlined one is a difference a user notices without being able to say why.
- **Palette** — deep teal `#0F6E6E` (care, without the coldness of medical blue)
  and warm amber `#C8791A` for everything *waiting on a person* — which in this
  product is almost always a quote awaiting validation.

## Theme

14 px base, tighter table rows, `size="small"` inputs. An ERP is read, not
browsed: an operator scanning ninety quotes wants ninety rows on screen.

Buttons are not uppercased. MUI's default turns "Valider le devis" into
something that reads as a warning, and on a screen where most buttons are
ordinary actions that is noise.

## Locators

Every element the GUI campaign touches carries a `data-testid`. A CSS class is
Emotion's to rename on any MUI upgrade and a visible string changes the moment
somebody improves the French — neither is a contract. The test ids are.

→ [10 — Testing](10-testing.md), and `qa/COVERAGE.md` for the surface-by-surface map.
