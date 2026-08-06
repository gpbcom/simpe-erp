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
   draft ──submit──▶ pending-validation ──validate──▶ sent ──accept──▶ accepted
     ▲                       │                          │
     │                       │                          └───reject───▶ rejected
     └────refuse-validation──┘
     │
     └──send──▶ sent            ┌──── a manager's path ────┐
```

| Transition | Who | From → to | Also requires |
|---|---|---|---|
| `submit` | author (assistant) | `draft` → `pending-validation` | priced; the caller wrote it |
| `validate` | manager | `pending-validation` → `sent` | priced |
| `refuse-validation` | manager | `pending-validation` → `draft` | — |
| `send` | manager | `draft` → `sent` | priced |
| `accept` | manager | any → `accepted` | priced |
| `reject` | manager | any → `rejected` | — |

`EDITABLE_STATUSES` is `{DRAFT}` and `SENDABLE_STATUSES` is `{DRAFT}`.
`SCHEDULABLE_STATUSES` is `{ACCEPTED}` — only an accepted quote reaches the
planner.

## Three decisions that are easy to get wrong

**Validating moves the quote to `SENT`, not to `ACCEPTED`.** A manager approving
a price is not a customer agreeing to it. Making validation produce `ACCEPTED`
would put work on assistants' calendars that no family had said yes to.

**Validating does not move it to `DRAFT` either**, which was the other obvious
option. An approved quote would then be indistinguishable from one nobody had
looked at, and the assistant could edit figures a manager had just signed off.

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
