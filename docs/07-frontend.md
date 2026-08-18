# 07 — Front-end

React 19 + TypeScript (strict) + MUI v6, built by Vite. `frontend/`.

## Stack, and why

| Concern | Choice | Because |
|---|---|---|
| UI | MUI v6 + MUI X DataGrid, date pickers | An ERP needs dense tables, date ranges and a consistent dark theme on day one |
| Server state | TanStack Query v5 | Caching, invalidation and loading states belong to one layer |
| Client state | Zustand — **the session only** | Everything else on screen is server state. Duplicating it is how two components disagree about the same quote |
| Routing | React Router v7 | — |
| Forms | React Hook Form + Zod | — |
| i18n | react-i18next, **French default** | The domain is French: CDI/CDD, +33 numbers, EUR, French holidays |
| Calendar | FullCalendar | The planning is a diary, not a list |
| Map | react-leaflet + OpenStreetMap | No API key, no billing, and it matches the Nominatim geocoding already in use |
| Tests | Vitest + Testing Library; Robot Framework for the GUI | — |

## Screens

```
/  and  /welcome             the landing page, signed in or out
/login                       (anything else, when there is no session)
/change-password             (rendered when must_change_password is set)

  assistant                          manager / administrator
  ─────────────────────────          ──────────────────────────
  /me            account             /quotes         every quote + queue
  /me/planning   calendar            /hcas           workforce
  /me/customers  portfolio           /map            intervention map
  /me/quotes     own quotes          /certifications qualification catalogue
  /me/team       their own team       /skills         skill catalogue
                                     /planning-settings planning rules
                                     /notifications
                                     /agencies       the company's sites  (admin)
                                     /teams          the teams            (admin)

  customer  (the portal — a different axis, not a lower rung)
  ──────────────────────────────────────────────────────────
  /portal/planning   their visits, with cancel and move
  /portal/quotes     their quotes, with a PDF download
  /portal/bills      their invoices, with a PDF download
  /portal/profile    their own details, editable
```

Signed in, `/` redirects to `/quotes` for a manager, `/me/planning` for an
assistant and `/portal/planning` for a household. An unknown route falls back to
the same place. **Three landings, not two**: a customer has none of the staff
screens, so sending them to the assistant's diary would be a redirect through a
page that answers 403.

**Signed out, the rule is deliberately the other way round from the obvious
one**: the landing page is *named* — `/` and `/welcome` — and the sign-in form
is the fallback. Making the welcome page the catch-all reads well until an
operator's session expires on `/quotes` and they are shown a product tour
instead of the password box they wanted. It also breaks every GUI suite, which
opens the root and expects to sign in. `Sign In As` navigates to `/login`
itself for that reason.

### `/welcome` — the landing page

Outside `AppShell`, full-bleed: the navigation rail and the account menu mean
nothing on a page that describes the product, and the hero wants the width.

It is reachable **signed in and signed out**, which decides its one control.
The session button cannot be labelled from a role — it says what the visitor
can do next. Signed out it reads "sign in" and goes to `/login`. Signed in it
names the user, reads "sign out", and ends the session **without going
anywhere else**: the signed-out application has no other page that means
anything to somebody who just chose to leave. The button is repeated at the
foot, because the page is long enough that reaching the end should not mean
scrolling back.

Nine cards, one per capability, each carrying an `AppIcon` glyph already used
on the screen it describes — so the tour and the product name things the same
way. Covered by `33_welcome.robot`, which asserts the count rather than
sampling: a landing page listing three of nine capabilities answers "does this
do my job?" with a maybe.

### The four that carry the requirements

**`/me` — the account page.** Contact details and address are editable. Contract
type and qualifications render as **locked chips with a tooltip naming who owns
them**, not as disabled inputs: a disabled input says "you cannot type here", a
locked chip says who to ask. The request model has no such fields at all, so
they cannot be smuggled in.

Two sections below it are the assistant's own to set, and they are
deliberately not the same control. `WorkingDaysSection` is seven toggleable
chips — the *recurring* week, "never Wednesdays" — and `AbsencesSection` is
a dated list. Before the first existed, saying "I never work Wednesdays"
meant filing one absence per Wednesday, forever. The save button submits the
**whole week**, never the chip that was clicked: two tabs open on the same
screen would otherwise race, and last-write-wins on a delta produces a week
nobody chose. Clearing every chip disables the button rather than sending a
request the server will refuse.

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

## Three words for three things

The word *agence* was already spent: the whole product called the `Company`
"l'agence", because there was only ever one place. There are now three levels
and each needs its own word.

| Concept | Code | French | English |
|---|---|---|---|
| The legal entity | `Company` | **Société** | Company |
| One of its places | `Agency` | **Agence** | Agency |
| People at a place | `Team` | **Équipe** | Team |

`nav.company` therefore changed from *"Mon agence"* to *"Société"*. Nothing else
was renamed.

**`TeamPlanningPage` keeps its name**, and so does every one of its
`team-planning-*` testids, although the component predates teams and means "the
whole company's planning". Renaming it would break a green suite for a cosmetic
reason. It gains a team picker whose controls carry fresh `team-picker-*`
testids, so suite 17 counts nothing it did not count before.

## The customer portal

The fourth identity, and the one place in the front-end where the role model is
**not** a ladder. `hca < manager < admin` is ranked and `hasAtLeast` walks it;
`customer` is a different axis — somebody the agency serves rather than somebody
who works for it.

**That distinction is enforced by the type, not by a convention.**
`hasAtLeast(role, minimum)` takes `minimum: StaffRole`, so
`hasAtLeast(role, 'customer')` **does not compile**. Written and allowed, it
would be satisfied by every employee — admitting staff to a household's
calendar, address and invoices. The same narrowing applies to
`RoleRoute minimum=` and to a nav entry's `minimum`, so neither can be gated on
a customer either. The portal uses `CustomerRoute`, which compares by identity,
and the nav uses a `customerOnly` flag. The server refuses the question the same
way — `rank()` raises. → [11](11-security.md#the-customer-is-not-a-rung-of-the-ladder)

### The login screen chooses a space

An Employee / Customer toggle above the fields, sent to `signIn` and validated
**after** authentication. A staff account signing in as a customer is signed
straight back out and told which side it belongs to.

That message is more specific than any other sign-in error, and deliberately so.
Everywhere else the form refuses to distinguish "unknown address" from "wrong
password", because that would make it an account-enumeration oracle. Here the
credentials have *already been accepted*, so naming the space discloses nothing
— and reporting it as "invalid credentials" would send somebody to reset a
password that works perfectly.

### What a household may change, and what they may not

`/portal/profile` carries the contact block and **nothing else**. Two fields are
absent on purpose:

- `registration_status` — a household who could set their own would promote
  themselves from prospect to active, which is exactly what makes the planner
  schedule their work.
- `billing_periodicity` — a commercial term the agency agrees.

Neither is a field the request model accepts, so leaving them off the form is
honest rather than decorative.

### Cancelling and moving say what they cost

Both send the whole quote back to `pending-validation`, so **none of its visits
are scheduled** until a manager re-validates — not only the one that changed.
The cancel dialog states that in as many words: a household who cancels one
Tuesday and finds their week empty would reasonably think the application had
broken.

The reschedule dialog asks for a **window**, not a time, because the solver
picks the moment inside it against the assistant's round. It pre-fills an hour
either side of the current visit — a window exactly as long as the work leaves
the solver nowhere to put it, so the visit returns unplaced, which reads as the
change having been ignored rather than refused.

The portal calendar **shows weekends**, unlike the assistant's diary. That
screen hides them because solved work is weekday work and two empty columns
waste width. A household asking "is anybody coming on Saturday?" is asking a
question the empty column answers.

## The language is server state now

The toggle in the top bar used to write `localStorage` and stop. That was
enough while it only decided what was on screen. It stopped being enough
once the quotes emailed to customers had to come out in it, because those
are built by a background webhook with no browser attached.

So switching the language now does two things: `setLanguage` applies it and
remembers it locally, and the same click `PATCH`es `/api/v1/me/account` to
store it. The session store adopts the stored value on sign-in and on
restore — signing in on a colleague's laptop should not leave the screen in
their language while every document goes out in yours.

`localStorage` is kept as well as the column, deliberately: it is what the
sign-in screen reads, before there is any account to read a preference from.

`AccountSection` sends the language back **unchanged** on every save. The
payload replaces the whole account, so omitting it would reset the holder to
French every time they corrected a typo in their own name — and the only
symptom would be a customer's quote arriving in the wrong language a
fortnight later. → [04](04-quote-lifecycle.md)

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


## The certification catalogue

**`/certifications`** (manager and above) is where the qualifications the
agency recognises are kept, and it is the only screen that can add one. It is
built like `/intervention-types` because it is the same kind of thing —
agency-managed reference data, retired rather than deleted — and two screens
that behave differently for no reason are two screens to learn.

Three things on it are worth explaining, because each is a rule rather than a
preference.

**The code column comes first, and the code is locked once the entry exists.**
It is what an assistant's stored qualification and a service's requirement are
matched on, so renaming it would disqualify every holder on the next planning
run. The server refuses it — the edit payload carries no `code` at all — and
the input is disabled with the reason beneath it. A locked field that does not
explain itself reads as a bug.

**Retired entries are listed, not hidden**, greyed with a status chip. A
manager wondering why they cannot require a qualification needs to see that it
exists and is retired. A screen that simply omitted it would answer that
question with silence.

**Deleting is offered and usually refused.** The server counts the assistants
holding the code and the services requiring it, and answers 409 naming both.
The message is shown verbatim, because it already says to retire the entry
instead — and retiring is one switch away in the same dialog.

## The skill catalogue, and the section that writes into it

**`/skills`** (manager and above) is the certification catalogue's twin, down to
the locked code, the listed-not-hidden retired entries and the 409 that offers
retirement. It is a separate screen rather than a tab on `/certifications`
because the two are edited by different people for different reasons, and a
single screen would have had to explain which half a manager was looking at.

What is **not** a twin is where the declarations come from. `SkillsSection` on
`/me` is the only place a skill is added, and it is the one control on that page
whose owner may change what the planner will assign them to.

Three things follow from that, and they are on screen rather than in a comment:

- **An alert says it takes effect immediately**, and that the managers are told.
  A control that silently widens what you may be sent to is one people use
  nervously, and the honest answer to "will somebody check this?" is *yes,
  afterwards*.
- **The picker offers only coded catalogue entries**, and hides what the
  assistant has already declared. A free-text skill matches no requirement, so
  it would be a record that looks right and satisfies nothing. A duplicate would
  be stored twice and read once.
- **The mutation invalidates `['planning']`**, like `field_employee` does. A
  declaration changes who the next run may schedule, so the calendars stop
  agreeing with the workforce until they are refetched.

The withdrawal control sits beside each chip. A manager removes anybody's from
`/hcas`. There is no control anywhere for a manager to *add* one, because there
is no endpoint — a supervisor may withdraw a claim they believe is wrong, but
not put one in somebody else's mouth.

## Qualifications are picked, never typed

The certification editor on `/hcas` used to be a free-text box. It is now a
select fed by the catalogue, and that is not a tidying-up: only a **coded**
qualification can be matched against a requirement, so a typed one is a record
that looks right on screen and satisfies nothing. The picker also hides what
the assistant already holds, so it cannot add a duplicate the server would
store twice and the planner would read once.

The same control appears on `/me` for a manager or an administrator editing
their own record, and as a **locked chip** for an assistant — the rule that an
assistant does not grant themselves a qualification, unchanged.

## Who goes out on the rounds

`field_employee` appears three times, and each rendering answers a different
question. A **labelled switch on the workforce grid** answers "who is out this
week" down the column *and* changes it in place. It was a read-only chip until
the only control that wrote it — a switch inside a dialog labelled "edit the
qualifications" — turned out to be somewhere nobody looks for "is this person
out this week": the field a manager changes weekly was the hardest one on the
screen to find. The dialog's switch stays, because that dialog edits the whole
employment record at once. The cell is the shortcut. And on `/me` it is an
editable switch for a manager and a **locked chip with a tooltip** for an
assistant: a disabled input says "you cannot type here", a locked chip says who
to ask.

The grid's cell keeps its **Oui / Non label** rather than showing a bare
switch. The column is scanned far more often than it is clicked, and a switch
alone says whether a thing can be changed without saying what it is. Each cell
holds its own mutation — a component per row, since a hook cannot be called
from a `renderCell` callback — and sends the row's contract and qualifications
back unchanged, because the route replaces all three fields.

The third rendering needs an account holding **both** a manager's role and an
assistant record — the section renders from the record and unlocks on the role.
None of the three staff accounts has a record, which is right for a back-office
manager but left that half of the screen unreachable, so the seeder promotes
one assistant to manager: `marc.dubois@simple-erp.fr`. Sign in as them to see
the editable form, and as `luc.martin@simple-erp.fr` to see the locked one.

**Both screens go through `useUpdateEmployment`**, which invalidates
`['planning']` as well as the workforce. Taking somebody off the rounds changes
who the next run may schedule, so the calendars stop agreeing with the
workforce screen until they are refetched. `/hcas` used to call the endpoint
directly and invalidate only its own grid — the same request, one refetch
short, which is the kind of difference that shows up as a calendar nobody can
explain.

## The working week, on two screens

The rota is editable in two places, because two people own the answer at
different times. `/me` carries `WorkingDaysSection` — the assistant's own
declaration — and `/hcas` opens `WorkingDaysDialog` from the days column,
where a manager sets anybody's.

The workforce grid printed the week as read-only chips for a long time, which
is the shape that reads as "this is fixed". It never was: the endpoint takes
any signed-in account and does a row-level ownership check, so a manager could
always set another assistant's week — there was simply no control for it.

**All seven days are offered, and the weekend is not special.** Nothing has
ever refused Saturday or Sunday. What makes them look barred is that the model
defaults to Monday-to-Friday, so every unedited record greys the last two — a
default that reads as a rule. Both screens offer all seven, and the manager's
hint says so in words.

Both apply the same two rules as each other, and for the same reasons: the
**whole week** is submitted rather than the day that was clicked, so two open
tabs cannot race into a week nobody chose. And a week with **no** day is
refused before the request, because the server answers 422 for it and a
disabled button says so before the click rather than after.

The dialog's chips are `rota-day-*`, deliberately clear of the grid's own
`working-day-*` — the GUI campaign counts the latter by prefix, and sharing it
would make one screen inflate the other's count.

## A requirement on a line, and the three states it has

Both quote dialogs carry the qualifications a line requires, beside the service
and the VAT category, and it is the same `LineCertifications` control in both.
`LineSkills` sits directly beneath it, doing the same job over the skill
catalogue — a separate control rather than more options in one picker, because
the two requirements are satisfied from different places and the planner reports
them as different reasons for leaving work unplaced.

Each exists to keep three states apart:

- **inherit** — the checkbox is ticked, and the service's own requirement is
  shown as read-only chips. "This visit needs DEAES" is something the operator
  should see *before* the planner tells them nobody is qualified for it.
- **override** — unticking hands them the inherited codes to edit, not an empty
  list. They said "let me change this", not "require nothing", and starting
  empty would silently drop a requirement they had not looked at yet.
- **require nothing** — an emptied override, which is a real answer when the
  catalogue's default is wrong for one customer.

Collapsing the last two would reinstate a requirement somebody had deliberately
removed, which is why the field is nullable on the wire and why the checkbox is
a separate control from the list.

Changing the service **drops both overrides**, rather than carrying them onto
work they were never about — an override of the *previous* service's
requirement would either demand a diploma the new one never asked for or keep
an empty override and quietly drop the one it does.

## Deleting a person, and saying what that costs

Both `/hcas` and `/customers` carry a delete control, and both open a
confirmation that names what will be destroyed before it asks. The customer's
counts the quotes that will go — fetched before anything is removed — because a
confirmation that does not say what it costs is a confirmation nobody reads.
The assistant's says the sign-in account goes too.

Both mutations invalidate `['planning']`. The visits are rewritten by a worker
behind the screen's back, so nothing else would refresh them — the same reason
`useDeleteIntervention` has always done it.

A refusal is shown **in the dialog**, not as a toast. The server's messages
here are the actionable part — which qualification is missing, how many people
hold it, that retiring is the alternative — and a message that disappears after
four seconds is a message nobody finished reading.

There is deliberately **no accounts screen**. An account is removed by removing
the assistant it belongs to, and `DELETE /api/v1/users/{id}` stays an API-only
operation for the fixtures a test campaign clears up.

## Screens added for the manager

**`/planning-settings` — the planning rules.** The agency's working day,
the midday break and its window, and the intervention radius. The four times
cross the wire as minutes from midnight, because that is the unit the solver
works in; `minutesToTime` and `timeToMinutes` convert at the edge so a
manager types a clock time. `timeToMinutes` returns `null` rather than `0`
for an unparseable value — a cleared input saved as midnight is a
plausible-looking number nobody chose.

It repeats the server's cross-field rules — a day that ends after it starts,
a lunch window inside that day and wide enough to hold the break — and the
repetition is for the *message*, not the guard: caught here it names the
conflicting pair before the request, and the server answers 422 for anything
sent past the form. The page also says in as many words that saving does not
re-plan anything, because a manager widening a radius to fix today's gap and
finding nothing changed has been misled unless the screen said so first.

The workforce grid carries a **working-week column** for the same reason the
feature exists at all: an assistant declaring "no Wednesdays" that only they
can see is a rota nobody can plan around.

**Writing a quote** — `NewQuoteDialog`, opened from the quotes screen. It sends
**no amounts**: the server prices every line against the catalogue, and a total
computed in the browser would be a second answer that disagrees with the stored
one the first time a rate changes. Its dropdowns are native `<select>` elements
rather than MUI's default, which renders a hidden input beside a div that
neither a test nor a keyboard can operate as a dropdown.

**The account screen** (`/me`) is in two halves, and the split is the point.

The **portrait**, `AccountSection` and `PasswordSection` describe the **account**
— the thing that signs in — and every caller has one. `MyAccountPage`'s
remaining sections describe an **assistant record**: the person a manager
schedules, with a home address the planner routes from, a contract and a
schedule. Managers and administrators have the first and not the second.

Conflating them was a real bug: the page fetched `GET /me/hca` unconditionally,
that route refuses an account with no assistant record, and so every manager and
administrator saw a single red error where their own details should have been.
The profile query is now `enabled` only when the account carries an `hca_id`,
and the assistant half is replaced by a sentence explaining its absence.

**The portrait moved across that line**, and for the same reason. It used to sit
inside the assistant half, so a manager or an administrator got no photograph at
all — not a locked control, simply a blank circle with nothing to click. It now
hangs off the account (`PUT /me/account/photo`), which every signed-in caller
has, and the card renders for all three roles. When the account *is* bound to an
assistant record the server writes the same URL there too, so the manager's map
pin follows the upload rather than staying on initials.

The file input is cleared after every pick (`event.target.value = ''`). Without
that, choosing the same file twice fires no second `change` event, and an upload
that failed could not be retried with the photograph that failed.

Two fields are editable — display name and sign-in address — and everything else
the account holds is **shown as a locked chip with a tooltip naming who owns
it**. Shown rather than hidden: a page that omits what it will not let you
change answers "what does this system say about me?" with silence. A disabled
input says "you cannot type here". A locked chip says who to ask.

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
labelled with the rate it implies — read from `GET /intervention-types/pricing-rules`
rather than written into a translation string, so the percentage on screen and
the one on the invoice come from the same place.

The line row is a **grid, not a flex row**. With `flex: N` (shorthand for
`flex: N 1 0%`) the two dropdowns were given a zero basis and shrank under their
own content, while the date input — which had no `flex` at all — kept its
intrinsic width and took the room. The controls ended up overlapping. Every
test-id-driven test passed straight through it, because Playwright fills a
control regardless of how wide it is drawn. Picking a service fills it in with what that
service usually is — the common case in one click — and leaves it editable,
because only the person writing the quote knows whether this customer's hours
fall under a care plan.

**The customer's file** (`/customers`, manager and above) — a searchable grid
of every household the agency serves, opening a drawer with everything held
about one of them and, first, **the arrangements currently being delivered**.
That is the question the screen is opened to answer; history sits below it.

**Registering a household starts here too**, from a button beside the search
rather than on a screen of its own. A manager taking a telephone enquiry looks
the family up first, and putting the control anywhere else would mean leaving
the one screen that can answer "do we already know them?" in order to say that
we do not. On success the new customer's drawer opens, because the next thing
that happens after registering a family is writing their first quote.

`CustomerDialog` requires **every** field, which is unusual for a form and
deliberate: a customer with no address cannot be routed to, and one with no
telephone number cannot be reached when an assistant is running late. It sends
**no coordinate** — the server geocodes while it validates, and a home the map
does not know is still registered with the failure recorded on the address, so
the dialog closes on success and the routing warning belongs on the file. It
registers a **prospect**, not a customer: the agency has taken the details, not
agreed to serve them.

**The filters live in the URL**, held by `useCustomerFilter` and written with
`useSearchParams`. A narrowed book is then a link somebody can send, it survives
a reload, and the back button undoes a filter — none of which works when the
same state sits in a `useState`. History entries are **replaced** rather than
pushed, or leaving the screen would take a press per filter.

Two speeds, because the controls are two gestures. Typing settles for 300 ms
before the URL moves. A status tab or a flag applies at once, since a click is
already a finished decision and delaying it reads as the control not working.
The search box used to fire a request **per keystroke**, and six text filters
make that materially worse.

The status tabs follow the quotes screen's idiom, with **prospects second** for
the same reason the validation queue is: it is the list somebody has to act on.
The other six filters fold away behind a button that carries a count, so a
hidden filter can never narrow the book invisibly. The two flags are native
`<select>`s with three options rather than checkboxes, because they have three
states — a checkbox cannot say "only those *without* an ongoing arrangement",
which is how a manager finds the families the agency quoted and then forgot.

Filtering runs on the **server**. The grid holds one page, so a filter applied
in the browser would search the rows it happens to have and silently miss the
rest of the book.

**Promote is offered only on a prospect**, in the drawer, where their quotes are
visible — that is the context the decision is taken in. Not disabled everywhere
else: disabled buttons on all ninety rows would bury the six that are waiting.
No `hasAtLeast` call either. The nav entry, the route and every customers
endpoint are already manager-gated, and `hasAtLeast` ranks admin above manager,
so "admin and manager" *is* the existing guard.

The drawer **re-reads the customer** rather than trusting the row that was
clicked. The row is whatever the last list fetch held, and promoting from inside
the drawer changes the record on the server — drawn from the prop, the chip
would still say *prospect* and the button would still be offered, for somebody
who is already active.

`CustomerStatusChip` is shared by the grid, the drawer and an assistant's own
portfolio. Each used to spell its own colour rule, which is exactly how
`prospect` would have arrived amber in one place and grey in the other two.
`REGISTRATION_STATUS_COLOUR` in `theme/palette.ts` is exhaustive over the enum,
so a status added to the backend without a colour is a TypeScript error rather
than an uninterpretable grey chip.

The two controls that end or extend care live on the arrangement card itself,
not on a settings screen. Both are decisions taken while looking at what the
arrangement currently delivers — which visits, from when, at what price — and a
screen that makes somebody remember a reference and go elsewhere is a screen
where the wrong quote gets cancelled.

This entry was in the navigation for a long time **with no route behind it**, so
clicking it fell through to the catch-all and silently redirected home.

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

**Plannings** — `/plannings`, open to every member of staff. The endpoint
already existed and only the map used it. The map answers *where*, while a
manager asking whether Monday is covered needs *who and when*.

**Two lenses, one screen.** An intervention names an assistant *and* a
household, so the same visits group two ways: **by assistant** answers "is
Thursday covered", **by customer** answers "what is happening at Madame
Vincent's this week". Neither is a filter over the other's answer, which is why
the switch is a two-segment control naming both states rather than a checkbox
whose unchecked half is unlabelled.

The switch is rendered **only for a manager**. An assistant opens the screen
directly on the households lens and is offered no segment: the assistants lens
is not theirs to read, and a control whose other side answers 403 is a control
that lies. Their households are scoped server-side to their own portfolio — the
ones they visit, union the ones they quoted — so the screen can hold nothing
they could not already reach.

**The households lens is the household's own calendar.** It reads the span
`customerPlanningWindow()` from `utils/planningWindow.ts`, which
`/portal/planning` reads too. It shows weekends, because care does not stop on a
Sunday and the family's own screen shows them. And narrowed to one household it
colours by status, which is what that family sees. On the whole-agency grid the
hue answers "whose visit is that" instead — there is no portal counterpart to a
view of forty households.

It is **read-only**. Retyping a visit reprices the quote it came from and
cancelling it takes it off the customer's bill; both stay on the assistants
lens, where a manager arrived to schedule rather than to answer a telephone
call.

It is a calendar — the same `FullCalendar` an assistant reads their own week
off, so the two screens read alike and a fix to one is a fix to both — with a
rail of assistants down the left. The rail opens on **All assistants**, because
"who is out this week" is what brings a manager here. Landing on the first
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
