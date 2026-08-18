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
job. It is not something this document can assert on its own.

---

## Routes

| Route | Suite | What is asserted |
|---|---|---|
| `/` (unauthenticated) | 12 | The sign-in card, whatever address was typed |
| `/` (manager) | 12 | Redirects to `/quotes` |
| `/` (assistant) | 12 | Redirects to `/me/planning` |
| `/me` | 02, 14, 23 | **Every role**, not only an assistant. Account fields; password controls. Locked fields. The assistant half when there is one; save; reload |
| `/me/planning` | 03, 08 | Three views, four navigation controls, event drawer |
| `/me/customers` | 03, 13 | Cards, search, empty state, drawer, scoping |
| `/me/quotes` | 03, 10, 20 | Grid, conditional submit, every status, editing own quote |
| `/quotes` | 04, 10, 16, 20 | Six tabs, sort, page, conditional actions, empty queue, writing and editing |
| `/hcas` | 04, 11 | Grid, avatars, search, empty search, editor |
| `/map` | 04, 09 | Tiles, pins, tooltips, windows, side list, zoom |
| `/notifications` | 07 | List, unread chip, mark-all, empty state |
| `/intervention-types` | 22 | Grid, agency rules shown read-only, inherited rate printed, rate set and stored, code locked, validity gate |
| `/customers` | 24 | Grid, search, no-match state, detail drawer, ongoing versus past arrangements |
| `/company` | 22 | Read without an identifier, saved, blank name refused, manager turned away by URL **and** by the server |
| `/certifications` | 25, 28 | Grid, what-this-is caption, add, locked code, malformed code refused, label edited, retirement, both delete refusals, delete of an unreferenced entry |
| `/skills` | 31 | Grid, what-this-is caption, add, locked code, malformed code refused, delete of an unreferenced entry |
| `/me` — my skills | 31 | An assistant declares one from their own account, the picker stops offering it, the alert says it takes effect at once, and a manager withdraws it |
| `/agencies` | 35 | Grid, what-this-is caption, the two counts, the roster dialog. A second head office refused. The legal identity absent from the projection. The empty-site delete and the head-office refusal |
| `/teams` | 35, 36 | Grid, site and manager resolved client-side, roster and shared-space dialogs. Duplicate name refused. The second-team refusal. Disband allowed and refused |
| `/me/team` | 36 | Read from the credential with no identifier to pass |
| unknown route | 12 | Falls back to the role's home |
| forbidden route | 12 | Assistant typing `/quotes`, `/hcas`, `/map` is redirected |

## Components and controls

| Surface | Suite | What is asserted |
|---|---|---|
| `AppShell` — logo, account | 06 | Both render. The frame survives a route change |
| `AppShell` — navigation | 06, 12, 22, 24 | Every entry reaches its screen (walked from each entry's own `href`, so a dead entry fails); **My account present for all three roles**; role filtering both ways |
| `AppShell` — language | 06 | Frame **and** body translate; choice survives a reload |
| `AppShell` — theme | 06 | Dark and back; stored value; repainted background |
| `AppShell` — sign out | 06 | Returns to the card **and** clears the token |
| `LoginPage` | 01 | Both roles; wrong password; unknown address. Identical message |
| `ChangePasswordPage` | 21 | The gate closing on a brand-new account, and opening once it changes |
| `NotificationBell` | 07 | Badge count, popover, unread emphasis, click-through |
| `NotificationsPage` | 07 | List, unread chip, mark-all, disabled when empty |
| `QuoteStatusChip` | 10, vitest | Amber for pending, outline for draft, label per status |
| `MyAccountPage` — employment | 26 | The on-the-rounds flag shown to an assistant as a **locked chip**, and refused to them by the server through both routes that could carry it |
| `MyAccountPage` | 02, 14, 23 | Portrait fallback, seven fields, save, snackbar, locked chips + tooltip, assistant half absent for a manager |
| `AccountSection` | 14, 23 | Name and address editable and saved. Dirty and validity gates; role, active, agency and binding locked and non-empty; conflict on a taken address shown **on the page** and not stored; privileged field ignored |
| `InterventionTypesPage` | 22 | Grid, pricing-rules card, inherited-rate rendering; **no VAT-category column**, since that is a per-quote decision |
| `InterventionTypeDialog` | 22, 28 | Rate saved server-side, code locked on an existing entry, negative rate blocked, required qualifications chosen from the catalogue and stored |
| `CustomersPage` / `CustomerDetailDrawer` | 24, 27 | Every held field; ongoing arrangements first. The delete control, its quote count, and the cascade |
| `QuoteArrangementCard` | 24 | Renewal switch asserted **server-side**. Interruption stores the date, halves the total, keeps the cancelled visit priced; both guards |
| `CompanyPage` | 22 | Fields, save, validity gate, applications caption, admin-only guard |
| `PasswordSection` | 14, 21 | All three fields; confirmation mismatch. All-three-required gate; wrong current password reported and *not* applied. A real change confirmed, verified server-side, old password refused |
| `MyPlanningPage` | 08 | Week/day/month, prev/next/today, day bounds, no weekends, drawer |
| `MyCustomersPage` | 13 | Cards, contents, search, no-match empty state, drawer open and close |
| `MyQuotesPage` | 10, 20 | Grid, submit and edit only on drafts, every authored status |
| `QuotesPage` | 10, 16, 20 | Six tabs, status chips, sort, paging, conditional actions, empty queue |
| `NewQuoteDialog` — layout | 16 | Every control on a line at least 60px wide and none overlapping, asserted from bounding boxes — the one check a test-id-driven suite cannot make |
| `NewQuoteDialog` | 16 | Reference, customer, service, **VAT category**, server-side pricing of what was sent — with the stored tax asserted as a ratio, so it survives a rate change |
| `QuoteEditorDialog` — VAT category | 20 | Chosen per line, stored, and the tax asserted to *rise* when it moves to comfort; suggested from the catalogue but overridable |
| `QuoteEditorDialog` | 20 | Opens on stored lines; save reprices. Add, remove, auto-naming; both guards; cancel changes nothing. The pricing hint |
| `QuoteEditorDialog` — scoping | 20 | Manager edits a quote they did not write. Assistant edits only their own, refused server-side on anybody else's. No edit button past draft |
| `HcasPage` | 11, 26, 27 | Grid, avatars, search, empty search, the on-the-rounds chip, the delete control |
| `HcasPage` — editor | 11, 26 | Open, cancel-changes-nothing, add+save, grid refetch, remove+save — the qualification **picked from the catalogue**, never typed, since only a coded one can be matched. The on-the-rounds switch saved and restored |
| `HcasPage` — deletion | 27 | Confirm dialog, its warning, and the sign-in account going with the record |
| `CertificationsPage` / `CertificationTypeDialog` | 25 | Every control, both validity gates, and the two refusals that stand in for a foreign key that cannot exist |
| `LineCertifications` | 28, vitest | Inherit versus override versus require-nothing — the three states asserted apart, since collapsing two of them silently reinstates a requirement somebody removed |
| `InterventionMapPage` | 09 | Tiles, attribution, pin count = list count, photo-or-initials, tooltip, three windows, counter, zoom |
| `AppIcon` | 06, 09, 11 | Rendered inside navigation, actions and pins |
| `RoleRoute` guard | 12 | Typed URLs, both directions |
| API client — 401 handling | 12 | A rejected token returns to the card and is discarded |
| API client — SSE | 05, 07 | Badge rises after a broker round trip |
| i18n — both bundles | 06 | Navigation and page body in English, then back |
| `formatMoney` / `formatTime` / `initialsOf` | vitest | Unit-tested directly |
| `AgencyDialog` | 35 | Name, type, address. The type overwritten by the server |
| `AgencyMembersDialog` | 35 | Both member kinds. Attach as a transfer, and detach |
| `TeamDialog` | 35 | Name, site and manager; only managers offered |
| `TeamMembersDialog` | 35 | One person at a time. The outside-the-site refusal |
| `TeamDocumentsDialog` | 35 | Upload, download, delete. The published limits |
| Scope picker on `/plannings` | 36 | One team, one site, or the whole company — the last offered to an administrator only |
| `AGENCY_TYPE_COLOUR` | 35 | Every site type rendered as its own chip |

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
| Catalogue entry requiring no qualification — the default | 28 |
| Quote line inheriting its service's requirement | 28 |
| Quote line requiring nothing, against its service | 28 |
| Certification retired but still held | 25 |
| Certification referenced, so undeletable | 25 |
| Assistant off the rounds | 26 |
| Deletion with nothing to replan — 204, no run queued | 27 |
| Planning refused: nobody holds the qualification | 28 |
| Agency-wide rules that cannot be edited on screen | 22 |
| Conflict — sign-in address already used | 23 |
| Brand-new account with no history | 21 |
| Customer with no ongoing arrangement | 24 |
| Arrangement ended early | 24 |
| Forced password change outstanding | 21 |
| Error — wrong credentials | 01 |
| Unread versus read | 07 |
| Light and dark theme | 06 |
| French and English | 06 |
| A company with more than one site | 35 |
| A manager who runs no team | 36 |
| A team with no shared document | 35 |
| A quote book narrowed to nothing by the team scope | 36 |
| A manager refused a company-wide computation | 36 |
| A manager refused another team's run, both writing it and polling it | 36 |

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
- **Suites 35 and 36 make their own site and their own team**, and remove them
  in that order — a site holding a team refuses to close, which is the same
  refusal suite 35 asserts. The seeded organisation is never touched: the seed
  deliberately keeps every seeded person and quote in **one** team so that every
  count the rest of the campaign asserts is unchanged, and a suite that needs a
  second team forms one rather than splitting the seeded workforce.

## Running it

```sh
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml up -d --build
pip install -r qa/requirements.txt
rfbrowser init
robot --outputdir qa/results qa/robot/suites
```

Then open `qa/results/report.html` for the functional result and
`qa/results/coverage/index.html` for the measured coverage.
