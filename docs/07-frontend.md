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


## Screens added for the manager

**Writing a quote** — `NewQuoteDialog`, opened from the quotes screen. It sends
**no amounts**: the server prices every line against the catalogue, and a total
computed in the browser would be a second answer that disagrees with the stored
one the first time a rate changes. Its dropdowns are native `<select>` elements
rather than MUI's default, which renders a hidden input beside a div that
neither a test nor a keyboard can operate as a dropdown.

**The account screen** (`/me`) is in two halves, and the split is the point.

`AccountSection` and `PasswordSection` describe the **account** — the thing that
signs in — and every caller has one. `MyAccountPage`'s remaining sections
describe an **assistant record**: the person a manager schedules, with a
portrait, a home address the planner routes from, a contract and a schedule.
Managers and administrators have the first and not the second.

Conflating them was a real bug: the page fetched `GET /me/hca` unconditionally,
that route refuses an account with no assistant record, and so every manager and
administrator saw a single red error where their own details should have been.
The profile query is now `enabled` only when the account carries an `hca_id`,
and the assistant half is replaced by a sentence explaining its absence.

Two fields are editable — display name and sign-in address — and everything else
the account holds is **shown as a locked chip with a tooltip naming who owns
it**. Shown rather than hidden: a page that omits what it will not let you
change answers "what does this system say about me?" with silence. A disabled
input says "you cannot type here"; a locked chip says who to ask.

**The catalogue** (`/intervention-types`, manager and above) is where an hourly
rate is set, and the only place that is. Nothing on a quote lets an operator
type an amount — the server prices from here. An entry that names no rate of its
own inherits the agency default, and the grid prints the **inherited figure**
rather than leaving the cell blank: an empty cell reads as "free", and the
difference between "inherits €31.905" and "costs nothing" is the difference
between a correct quote and one that bills a family nothing.

The agency-wide rules are shown beside it and **not editable there**, with a
caption saying why. A read-only field that does not explain itself reads as a
bug.

**The agency** (`/company`, administrator only) carries the trading name, SIRET,
contact and registered address, and the switch that decides whether the agency
appears on the list a prospective assistant applies through. Closing it does not
discard the applications already waiting, and the caption says so — "stop
accepting applications" reads like it might.

**Navigation.** Entries are filtered by role rather than disabled: an entry a
caller may not use is absent, not greyed out. Two defects lived in that list and
are worth recording, because both were invisible to the person who could fix
them. `/me` was marked assistant-only, so a manager saw a "Mon compte" heading
with only "Mes devis" beneath it — a section named after a screen it did not
contain, and the account page having been fixed made no difference because
nothing led to it. And `/customers` had an entry with no route behind it, so
clicking it silently redirected home, which reads as the click not registering.

Both quote dialogs carry a **VAT category per line**, beside the service and
labelled with the rate it implies. Picking a service fills it in with what that
service usually is — the common case in one click — and leaves it editable,
because only the person writing the quote knows whether this customer's hours
fall under a care plan.

**Editing a quote** — `QuoteEditorDialog`, one component used by both the
manager's grid and the assistant's. A manager editing any quote and an assistant
editing their own do exactly the same thing to it; what differs is which quotes
they can open and which endpoint saves them, expressed as a single `scope`
prop. Two dialogs would be two places for the line rules to drift apart.

Like `NewQuoteDialog` it sends **no amounts** — it shows the stored total beside
a note saying the server recomputes on save, rather than a figure it worked out
itself. Its service picker is a native `<select>` for the same reason as its
sibling's.

The Edit button renders only on a draft, and on the assistant's grid only on
quotes they wrote. Neither is the control: the server checks both, and suite 20
sends the forbidden request by hand to prove it.

**Team planning** — `/plannings`, manager-gated. The endpoint already existed
and only the map used it; the map answers *where*, while a manager asking
whether Monday is covered needs *who and when*.

It is a calendar — the same `FullCalendar` an assistant reads their own week
off, so the two screens read alike and a fix to one is a fix to both — with a
rail of assistants down the left. The rail opens on **All assistants**, because
"who is out this week" is what brings a manager here; landing on the first
assistant alphabetically would answer a question nobody asked and hide the rest
behind a click. Choosing a name narrows the grid to that person alone.

The two modes colour their blocks differently, and deliberately. On the shared
grid the question is *whose visit is that*, so each assistant gets a colour from
`PLANNING_HCA_COLOURS` and wears it in the rail as a legend; forty blocks in the
four status colours are unreadable. Narrowed to one assistant, "who" is already
answered by the rail, so the blocks go back to the status colours used
everywhere else.

A block opens a drawer naming the **assistant in full**, the customer, the time
and the address. The name is there because on the shared grid the block was told
apart by its colour, and a colour is not something anybody can act on: "who do I
ring about this visit" has to be answerable in words.

**Promotion** — on the workforce row, beside the person it concerns rather than
on an accounts list that would ask a manager to find the same person twice by
email. Both `/users` and `/users/{id}/promote` are **administrator-only**, so
the role column and the button are hidden from a manager entirely: showing "no
account" against every assistant would state a fact about the agency when it is
really one about the reader's permissions. The query is disabled rather than
left to 403, because a failed query renders as an empty list.
