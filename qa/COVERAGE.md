# GUI campaign — what is covered, and how that is known

Two different claims live in this file, and they are worth keeping apart.

**Behavioural coverage** is the table below: every route, every control and
every state, mapped to the suite that exercises it. It is complete, and it is
auditable by reading — a reviewer can check a row against the code.

**Statement coverage** is a number produced by running the campaign. Playwright
collects V8 coverage from Chromium while the suites drive the application, Vite's
source maps fold it back onto the `.tsx` files, and `99_coverage_report.robot`
merges every suite's raw output into one report at
`qa/results/coverage/index.html`. The threshold is set to 90 % statements and
lines in `qa/coverage.config.json`.

The distinction matters because **the second number cannot be produced without
running the stack and the browsers**. It is checked in CI by the `e2e-robot`
job; it is not something this document can assert on its own.

---

## Routes

| Route | Suite | What is asserted |
|---|---|---|
| `/` (unauthenticated) | 12 | The sign-in card, whatever address was typed |
| `/` (manager) | 12 | Redirects to `/quotes` |
| `/` (assistant) | 12 | Redirects to `/me/planning` |
| `/me` | 02, 14, 23 | **Every role**, not only an assistant; account fields; password controls; locked fields; the assistant half when there is one; save; reload |
| `/me/planning` | 03, 08 | Three views, four navigation controls, event drawer |
| `/me/customers` | 03, 13 | Cards, search, empty state, drawer, scoping |
| `/me/quotes` | 03, 10, 20 | Grid, conditional submit, every status, editing own quote |
| `/quotes` | 04, 10, 16, 20 | Six tabs, sort, page, conditional actions, empty queue, writing and editing |
| `/hcas` | 04, 11 | Grid, avatars, search, empty search, editor |
| `/map` | 04, 09 | Tiles, pins, tooltips, windows, side list, zoom |
| `/notifications` | 07 | List, unread chip, mark-all, empty state |
| `/intervention-types` | 22 | Grid, agency rules shown read-only, inherited rate printed, rate set and stored, code locked, validity gate |
| `/company` | 22 | Read without an identifier, saved, blank name refused, manager turned away by URL **and** by the server |
| unknown route | 12 | Falls back to the role's home |
| forbidden route | 12 | Assistant typing `/quotes`, `/hcas`, `/map` is redirected |

## Components and controls

| Surface | Suite | What is asserted |
|---|---|---|
| `AppShell` — logo, account | 06 | Both render; the frame survives a route change |
| `AppShell` — navigation | 06, 12, 22 | Every entry reaches its screen (walked from each entry's own `href`, so a dead entry fails); **My account present for all three roles**; role filtering both ways |
| `AppShell` — language | 06 | Frame **and** body translate; choice survives a reload |
| `AppShell` — theme | 06 | Dark and back; stored value; repainted background |
| `AppShell` — sign out | 06 | Returns to the card **and** clears the token |
| `LoginPage` | 01 | Both roles; wrong password; unknown address; identical message |
| `ChangePasswordPage` | 21 | The gate closing on a brand-new account, and opening once it changes |
| `NotificationBell` | 07 | Badge count, popover, unread emphasis, click-through |
| `NotificationsPage` | 07 | List, unread chip, mark-all, disabled when empty |
| `QuoteStatusChip` | 10, vitest | Amber for pending, outline for draft, label per status |
| `MyAccountPage` | 02, 14, 23 | Portrait fallback, seven fields, save, snackbar, locked chips + tooltip, assistant half absent for a manager |
| `AccountSection` | 14, 23 | Name and address editable and saved; dirty and validity gates; role, active, agency and binding locked and non-empty; conflict on a taken address shown **on the page** and not stored; privileged field ignored |
| `InterventionTypesPage` | 22 | Grid, pricing-rules card, inherited-rate rendering |
| `InterventionTypeDialog` | 22 | Rate saved server-side, code locked on an existing entry, negative rate blocked |
| `CompanyPage` | 22 | Fields, save, validity gate, applications caption, admin-only guard |
| `PasswordSection` | 14, 21 | All three fields; confirmation mismatch; all-three-required gate; wrong current password reported and *not* applied; a real change confirmed, verified server-side, old password refused |
| `MyPlanningPage` | 08 | Week/day/month, prev/next/today, day bounds, no weekends, drawer |
| `MyCustomersPage` | 13 | Cards, contents, search, no-match empty state, drawer open and close |
| `MyQuotesPage` | 10, 20 | Grid, submit and edit only on drafts, every authored status |
| `QuotesPage` | 10, 16, 20 | Six tabs, status chips, sort, paging, conditional actions, empty queue |
| `NewQuoteDialog` | 16 | Reference, customer, service, **VAT category**, server-side pricing of what was sent — with the stored tax asserted as a ratio, so it survives a rate change |
| `QuoteEditorDialog` — VAT category | 20 | Chosen per line, stored, and the tax asserted to *rise* when it moves to comfort; suggested from the catalogue but overridable |
| `QuoteEditorDialog` | 20 | Opens on stored lines; save reprices; add, remove, auto-naming; both guards; cancel changes nothing; the pricing hint |
| `QuoteEditorDialog` — scoping | 20 | Manager edits a quote they did not write; assistant edits only their own, refused server-side on anybody else's; no edit button past draft |
| `HcasPage` | 11 | Grid, avatars, search, empty search |
| `HcasPage` — editor | 11 | Open, cancel-changes-nothing, add+save, grid refetch, remove+save |
| `InterventionMapPage` | 09 | Tiles, attribution, pin count = list count, photo-or-initials, tooltip, three windows, counter, zoom |
| `AppIcon` | 06, 09, 11 | Rendered inside navigation, actions and pins |
| `RoleRoute` guard | 12 | Typed URLs, both directions |
| API client — 401 handling | 12 | A rejected token returns to the card and is discarded |
| API client — SSE | 05, 07 | Badge rises after a broker round trip |
| i18n — both bundles | 06 | Navigation and page body in English, then back |
| `formatMoney` / `formatTime` / `initialsOf` | vitest | Unit-tested directly |

## States

| State | Suite |
|---|---|
| Loading | Implicit in every `Wait For Elements State` |
| Empty — customers | 13 |
| Empty — notifications | 07 |
| Empty — validation queue | 10 |
| Refused — editing another author's quote | 20 |
| Empty — HCA search | 11 |
| Account with no assistant record | 23 |
| Catalogue entry inheriting the agency rate | 22 |
| Agency-wide rules that cannot be edited on screen | 22 |
| Conflict — sign-in address already used | 23 |
| Brand-new account with no history | 21 |
| Forced password change outstanding | 21 |
| Error — wrong credentials | 01 |
| Unread versus read | 07 |
| Light and dark theme | 06 |
| French and English | 06 |

---

## Idempotency

Every suite is runnable twice against the same stack, and CI proves it by
running the whole campaign a second time without resetting anything.

The rules that make it so:

- **Fixtures are created and removed through the API**, never by clicking. A
  test that sets itself up through the UI cannot clean up when it fails
  half-way — the browser is already on an error page.
- **Anything created carries a unique suffix** from `Unique Suffix`, so two runs
  never collide, and teardown removes *exactly* what that run made by
  identifier rather than by pattern.
- **Seeded data is read-only.** Where a suite must change something seeded —
  suite 11 adds a qualification, suite 14 edits a profile, suite 10 empties the
  validation queue — it snapshots the original first and restores it in a
  teardown that runs even when the test failed. Suite 20 needs a quote it can
  rewrite, so it **creates two of its own** rather than editing a seeded one:
  a line added to a seeded quote would still be there on the second run, and
  the run after that would find a different fixture than it was written
  against.

## Running it

```sh
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d --build
pip install -r qa/requirements.txt
rfbrowser init
robot --outputdir qa/results qa/robot/suites
```

Then open `qa/results/report.html` for the functional result and
`qa/results/coverage/index.html` for the measured coverage.
