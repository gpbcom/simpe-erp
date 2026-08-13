# 04 — Quote lifecycle

## Why there is a validation step

An assistant sitting in a family's kitchen knows what that family needs. They do
not set the agency's prices. Before this existed, a quote could only be written
by a manager — which meant the person with the information was never the person
with the keyboard, and the details were relayed twice before anything was
priced.

So an assistant writes the quote, and it waits.

## The state machine

```
              ┌──── an assistant's path ────┐
              │                             │
   draft ──submit──▶ pending-validation ──validate──▶ accepted
     ▲                       │
     │                       │
     └────refuse-validation──┘
     │
     └──send──▶ accepted        ┌──── a manager's path ────┐

   sent ──accept──▶ accepted    ┌── legacy rows only ──┐
        └─reject──▶ rejected
```

**Nothing produces `sent` any more.** Both approval paths end at `accepted`:
`send` for a manager's own hand-written quote, `validate` for an assistant's
write-up. The status and its two transitions are kept because quotes stored in
it before that change still exist and need a way forward — see
[Validating is committing](#validating-is-committing).

| Transition | Who | From → to | Also requires |
|---|---|---|---|
| `submit` | author (assistant) | `draft` → `pending-validation` | priced; the caller wrote it |
| `validate` | manager | `pending-validation` → `accepted` | priced; stamps the issue dates and the approver as validator |
| `refuse-validation` | manager | `pending-validation` → `draft` | — |
| `send` | manager | `draft` → `accepted` | priced; stamps the issue dates and the sender as validator |
| `accept` | manager | any → `accepted` | priced |
| `reject` | manager | any → `rejected` | — |

| `replace lines` | manager, or the author | `draft` → `draft` | drafts only; reprices |

`EDITABLE_STATUSES` is `{DRAFT}` and `SENDABLE_STATUSES` is `{DRAFT}`.
`SCHEDULABLE_STATUSES` is `{ACCEPTED}` — only an accepted quote reaches the
planner.

## Which team gets it

A quote is attributed to a **team** the moment it is written, and the rule lives
in one place — `TeamService.attribute`, called from `QuoteService.create`, which
both writing paths funnel through. Two copies would drift, and the assistant's
path at `POST /api/v1/me/quotes` is the one that would be forgotten.

The rule, in order, each step there because the one before it can tie:

1. every team of the company is a candidate;
2. keep those whose **site is nearest** the household, within a half-kilometre;
3. among those, the one carrying the **fewest assigned minutes** — measured over
   *live quotes* rather than planned visits, so a company that has never run the
   planner still spreads its work;
4. among those, **the first by identifier**. Without a total order, two equally
   close and equally busy teams come back in either order and the same household
   is filed differently on two identical runs.

A site with no coordinate is **not** treated as a distance of zero: an
unresolved address read that way sits off the coast of Africa and would be
nearest to everybody. When nothing can be measured the busyness tie-break
decides alone, and the run says so at `WARNING` rather than claiming a proximity
nothing supports.

A quote that can be attributed to **no** team is **refused, 422**, naming which
of the two causes applied — an unknown household, or a company with no team.
Stored unattributed it would be priced, sent, accepted, and then read by no
planning run: it would go *quiet* rather than wrong, which is the failure mode
worth refusing for. A household whose address simply has not geocoded is not
refused; that would let a Nominatim outage stop the business taking work.

Renewals **inherit** the parent's team rather than re-running the rule. The
household has not moved and the arrangement has not changed; re-attributing
would hand a continuing customer to whichever team was least busy that morning,
and the assistants they know would stop coming.

`PATCH /api/v1/quotes/{id}/team` exists for the two cases the rule cannot see: a
proximity decision that was wrong, and a household that has moved. It is
deliberately manual — moving work automatically would move visits somebody has
already been told about — and it checks **both ends**, because taking work out of
a team empties a colleague's plan and putting it in commits assistants the
caller does not manage.

## Three decisions that are easy to get wrong

**Validating moves the quote to `SENT`, not to `ACCEPTED`.** A manager approving
a price is not a customer agreeing to it. Making validation produce `ACCEPTED`
would put work on assistants' calendars that no family had said yes to.

**Sending a hand-written quote moves it to `ACCEPTED`, and that is not the same
rule contradicted.** The two paths differ in what the agency knows. On the
assistant's path the offer goes out and the family has not answered yet, so
`SENT` is the honest state. A manager writing a quote by hand is recording an
arrangement they have already settled — and nothing in the agency ever moved
such a quote further: there is no accept button anywhere, so it sat outside
`SCHEDULABLE_STATUSES` and the visits somebody had promised were never planned.
Sending it *is* the agreement, so `send` stamps `issued_on`, `valid_until`, and
the sender as `validated_by`, the same way `validate` does. If a family later
changes its mind, `reject` says so.

**Validating does not move it to `DRAFT` either**, which was the other obvious
option. An approved quote would then be indistinguishable from one nobody had
looked at, and the assistant could edit figures a manager had just signed off.

**The tax is decided when the quote is written, not when the service was
catalogued.** Each line carries its own `service_category`, and pricing reads it
from there. `QuoteService.vat_rate_for` takes the *line*; if it ever takes an
`InterventionType` again, two customers buying the same service could no longer
be taxed differently, which is the case the field exists for.

**The qualification a line needs follows the same shape, with one state more.**
`required_certification_codes` is `null` by default, meaning "whatever the
catalog entry requires" — unlike the VAT category, most lines have no reason to
disagree with the catalogue, so inheriting is the sensible default rather than
an omission. A list overrides it, and an **empty** list means "this hour needs
no qualification at all", which is a real answer when the catalogue's default is
wrong for one customer.

That third state is why the field is nullable. Collapsing `[]` into `null`
would silently reinstate a requirement the person writing the quote had
deliberately removed, and neither the screen nor the stored row would show that
it had happened. `QuoteLine.effective_certification_codes` resolves the
fallback in one place, and the requirement builder calls it once per line so the
solver never has to know the rule exists.

A code the catalogue does not offer is a **422** on the way in, naming the code.
Leaving it to the planner would fail every run touching that line with a
message reading as a staffing problem when it was a typo.

## Ending an arrangement early

`interrupted_on` is the last day a quote is delivered. It is **inclusive**: a
family cancelling "from the 15th" means the 15th is the last visit, and reading
it the other way takes away a visit somebody is expecting.

Three things follow from it, and they are the whole feature:

- **The planner stops.** `build` drops lines dated after the interruption —
  filtered per *line*, not per quote, because the visits before the end date are
  still owed and a query that dropped the whole quote would cancel this week's
  work too.
- **The price follows.** `price_quote` aggregates over `effective_lines()`, and
  the totals are sums of the aggregates, so a shortened quote costs what it
  still delivers. Repricing happens when the interruption is *set*, not on every
  read: an issued quote must reprint identically, so amounts are stored.
- **The cancelled visits stay.** They keep their own amounts and stop counting.
  A family asking why the invoice came in under the quote they signed needs to
  see both figures, and a deleted line answers nothing. It also means an
  interruption can be *moved* — a family extending their notice reprices from
  lines that are all still there.

Keeping them priced matters for a second reason: an unpriced line on an accepted
quote trips `is_priced`, which would make the whole quote unschedulable — the
interruption would cancel the arrangement rather than end it.

An interruption before the first service is refused. It would leave an accepted
quote that costs nothing, delivers nothing and still reads as live; rejecting or
deleting the quote says what happened, and an end date in the past does not.

## Renewing one

`auto_renew` records that a customer wants the arrangement to continue.
`POST /api/v1/quotes/renewals/run` writes a **successor** for every accepted,
auto-renewing quote whose `valid_until` has passed.

A successor rather than an extension: extending `valid_until` in place would
rewrite what the customer accepted and lose the boundary between one period and
the next — and the price. The successor's services are the parent's, shifted
forward by the span the parent covered, so a Monday-and-Friday arrangement stays
on Mondays and Fridays. It is priced against the catalogue **as it stands now**,
so a rate change reaches the next period rather than the one already agreed.

**The sweep is idempotent, and that is the design.** `renewed_from_id` records
the parent, and a parent that already has a successor is skipped. Two workers
waking together, a retry after a partial failure, or a manager pressing the
button because the timer looked stuck — each leaves one successor, not two.
Nothing else would be safe to put on a timer.

An interrupted arrangement is never renewed: an end date is the customer saying
stop. That is checked in the service as well as in the query, because a quote
interrupted between the two would otherwise be renewed anyway.

**Nothing calls the sweep automatically yet.** The endpoint exists and is safe
to call as often as you like; binding it to the worker or a timer is still to do.

**Who may rewrite a quote is a different question from when.** A manager or an
administrator may edit any quote in the agency; an assistant may edit only the
ones they authored. But *both* are held to `EDITABLE_STATUSES`, so neither can
touch a quote past `draft`: what the customer was sent has to stay what they
were sent, and one awaiting validation is frozen so a manager rules on the
figures they were actually shown. Widening the role does not widen the status.

**Refusal returns the quote to `DRAFT`, not to `REJECTED`.** `REJECTED` means
*the customer declined*. A manager sending a quote back means the agency will
not make that offer as written. Collapsing the two would lose opposite facts
about the same customer — and would leave an assistant unable to correct and
resubmit.

## A quote awaiting validation is frozen

`EDITABLE_STATUSES` excludes `PENDING_VALIDATION`, so the lines cannot change
while a manager is looking at them. A manager must decide on the figures they
were shown, not on figures that moved underneath them.

## `send` has a precondition it did not used to have

`send()` originally had **no status check at all** — it would re-send an already
accepted quote, overwriting the customer's answer with the offer. It is now
`{DRAFT}` only, which also closes the route around the validation step: a
submitted quote cannot be issued without somebody ruling on it, and
`validated_by` cannot be left empty on a quote that reached a customer.

## Who did what

Four columns record it, and they are the reason the workflow is auditable.

| Column | Written by | Means |
|---|---|---|
| `authored_by` | `create`, from the **caller's credential** | Who wrote it. Scopes the assistant's own list |
| `submitted_at` | `submit` | When it entered the queue |
| `validated_by` | `validate` **and** `refuse-validation` | Who *ruled* — a refusal is a decision somebody owns too |
| `validated_at` | both | When |

The author is never taken from the payload. A quote naming somebody else would
land in their list, and they would be the one a manager asks about a price they
never set.

Before this, nothing recorded who accepted a quote at all.

## Pricing

Pricing runs when the lines change, and **never on read**. The stored amounts
are the offer; recomputing at display time would silently reprice an issued
quote after its catalog entry moved.

```
line total = hourly rate × (duration ÷ 60) × surcharge multiplier
VAT        = necessity 5.5 %  ·  comfort 20 %
```

Surcharges are **not cumulative** — a date matching several rules takes the
single largest, so 1 January falling on a Sunday bills at +50 %, not +75 %.
Rounding is `ROUND_HALF_UP`, the invoicing convention; Python's default
`ROUND_HALF_EVEN` would send 95.715 down to 95.71, a cent somebody has to be
told about.

Aggregates are computed per intervention type per ISO week, with the week's
Monday derived from 4 January — anchoring on 1 January is wrong for every year
starting on a Friday, Saturday or Sunday.

## What happens on submit

1. `QuoteService.submit_for_validation` checks the caller wrote it, that it is a
   draft, and that it is priced.
2. The status is stored. **This is synchronous and durable.**
3. `quote.submitted` is published to the broker — best effort.
4. The worker writes one notification per supervisor and the API pushes it over
   SSE.

If step 3 or 4 fails, the quote is still submitted and still in the manager's
queue, because that queue is a database query on
`status=pending-validation`, not a message. → [05](05-events-and-notifications.md)

## Where this is enforced

| Rule | Where | Tested by |
|---|---|---|
| Only the author may submit | `QuoteService.submit_for_validation` | `tests/service/test_quote_validation.py` |
| Only a draft may be submitted | same | same |
| Only a submitted quote may be validated | `QuoteService.validate` | same |
| A submitted quote cannot be sent | `QuoteService.send` | same |
| The author comes from the credential | `QuoteService.create` | same, and `tests/api/test_me_endpoints.py` |
| The whole journey, across two roles | — | `qa/robot/suites/05_quote_validation_journey.robot` |


## Validating is committing

There is no second button. A manager's approval *is* the act of issuing the
offer **and of committing the work**, so validation stamps `issued_on` and a
`valid_until` 30 days out (`QuoteService.VALIDITY_DAYS`) alongside moving the
quote to `accepted`.

**It used to stop at `sent`**, needing a separate acceptance before any of the
work was scheduled — and nothing on any screen asked for that step. The quote
left the validation queue, looked approved, and its visits never reached a
planning run: a manager validated a fortnight of work, re-ran the computation
and saw the same visit count, with nothing anywhere explaining the difference.

The asymmetry made it worse. `send` has always accepted a manager's own draft
outright, on the reasoning that they write one up for an arrangement already
settled with the family. That reasoning applies just as well to an assistant's
write-up: by the time it reaches the queue the customer has agreed, and what a
manager is ruling on is the agency's figures. The two paths now end in the same
place, which is what the two buttons always looked like they did.

It did not always. `record_validation` set the status, the approver and the
timestamp and left both dates null, so a quote reached its issued state with no
issue date and no expiry — the customer's copy carried neither. Only the seeder wrote them,
which meant seeded and runtime quotes disagreed about what a sent quote looks
like.

**A refusal stamps nothing.** It sends the quote back to its author, and putting
an issue date on an offer that was never made would date a document the customer
never received.

## The document the customer receives

An accepted quote is emailed as an `.xlsx` workbook by the planning-completed
webhook, built by `Formatter.format_quote`. It carries four blocks, and each of
them answers a question the customer would otherwise have to ask:

| Block | Holds |
|---|---|
| Issuer | Trading name **and legal form**, address, SIRET, RCS entry, intra-community VAT number, share capital, telephone and contact address |
| Recipient | The customer's full name and their address |
| Summary | The period the care runs over, how many interventions, the total duration, and the total including VAT |
| Table | One row per intervention: date, service, **quantity in hours**, unit price excl. VAT, **VAT rate**, amount excl. VAT, VAT, amount incl. VAT |
| Totals | Untaxed amount, **one line per VAT rate**, then the grand total |
| Terms | Validity, payment terms, late-payment penalties, the acceptance mention and a signature block |

**The quantity is hours, not minutes.** The unit price beside it is an hourly
rate, so a customer checking quantity × price against the amount has to be able
to reach the amount — minutes would make the arithmetic on the page wrong by a
factor of sixty.

**The tax is stated per rate, and that is a legal requirement rather than a
courtesy.** Home care is billed at 5.5% for a necessity service and 20% for a
comfort one. A single "VAT" figure gives the customer no way to check either and
an accountant no way to post it, so `Quote.vat_by_rate()` groups the priced lines
by the rate their category carries.

**The totals are summed from the lines the document prints**, not from the
quote's aggregates. The two agree on a priced quote, but the aggregates are
computed by the pricing service and a quote reaching the renderer without them
would print zero under a column of real amounts — and look correct doing it. On
a document somebody is asked to sign, a total that disagrees with its own column
is the worst failure available.

## What makes it a quote rather than a price list

French law is specific about what a commercial offer must carry, and the footer
is where the rest of it goes:

- how long the offer stands — omitted when the quote has no `valid_until`, because an offer promising to stand "until None" is worse than one promising nothing;
- when payment falls due, quoting the reference;
- what happens if it does not — three times the statutory rate plus the fixed 40 € recovery charge (Commercial Code art. L441-10);
- «&nbsp;Devis reçu avant exécution des travaux&nbsp;», and a dated signature block.

The wording is translated but **the obligations are not**: the agency is French
and so is the contract, so the English document carries the same mentions in
English. The language decides the words, not the law.

**The issuer used to be missing entirely**, and that was the serious gap. A
quote naming only its recipient is a document the recipient cannot act on: they
have no way to tell who is offering, under what registered number, or where to
reply — nor whether it is genuine. The agency comes from the **account that
issued it**, because neither a customer nor a quote carries a `company_id` of
its own; the webhook resolves it from the account that requested the planning
run, and answers 409 rather than sending a quote with no issuer.

The summary's period comes from the **lines**, not from `issued_on` and
`valid_until`. Those two describe the offer; a customer asking "when does the
care run from and to" is asking about the work.

Amounts are written as numbers with a currency format, never as pre-formatted
strings — the first thing anybody does with a quote is add up a column. An
unpriced line gets **empty** amount cells rather than zeroes: a zero reads as
"free", an empty cell reads as "not priced yet", which is what it is.

## The language it is written in

The document and its covering email come out in the language stored on the
account that requested the planning run — one catalogue, so the note and the
attachment always agree. Even the filename is translated (`devis-…xlsx` /
`quote-…xlsx`): it is the first thing the recipient sees, and often the only
thing they see before deciding whether to open it.

**The preference is stored on the account rather than read from a header**, and
that is forced by where the documents are built. The planning-completed webhook
runs in the background with no browser attached and no request to read
`Accept-Language` from. Until migration 0015 the choice lived only in the
front-end's `localStorage`, so the quotes went out in French whatever the
operator had selected and nothing on screen said so.

The interface writes the preference through `PATCH /api/v1/me/account` when the
language is switched, and adopts the stored value on sign-in. Adopting it back
is what keeps the two ends honest: signing in on a colleague's laptop should not
leave the screen in their language while every document goes out in yours.

French is the default everywhere. This is a French agency, and a quote reaching
a customer in English because nobody set a preference is the wrong failure to
default into. An **unknown** code is refused rather than falling back — a
preference the holder set and the server quietly ignored is worse than one it
rejected, because the screen would go on showing their choice.

## Pricing and the seed

A quote past `draft` **must have priced lines** — `validate` refuses one that
does not, with "has no priced lines and cannot be validated".

The seeder writes through the repositories rather than the service, so pricing
did not run and every seeded quote past draft carried unpriced lines: the whole
seeded validation queue failed on the first click. It now borrows `QuoteService`
the same way it borrows the password hasher, so seeded amounts come from the
application's own pricing rather than figures written into the dataset. Figures
typed into a fixture drift from the catalogue the first time a rate changes, and
the drift shows up as a screen that disagrees with itself.


## Editing

**A quote's lines are editable in every status.** They used to be editable only
while it was a draft, and what that protected is worth stating plainly: an
issued quote is what the customer is looking at, so changing it underneath them
is how somebody accepts one thing and is billed for another. Nothing records the
figures an edit replaced, so that history is not recoverable from the quote —
only the logs say a replacement happened, and not what it replaced. An edit also
reprices against the catalogue **as it stands now**, so editing an old quote can
move its amounts even where the lines are untouched.

What did not widen is *who* may edit. The authorship check is unchanged: an
assistant edits only what they wrote. Nor did **sending** — still drafts only,
because re-sending a quote the customer has answered would overwrite their
answer with the offer.
