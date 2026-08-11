# SimpleERP — documentation

Fifteen chapters. Each answers a different question, and the table says which.

If you are new to the codebase, read **01** and **02** and stop there — they are
enough to find your way around. Come back for the rest when you need them. **01
is long**: it opens with a diagram of what runs and what talks to what, and that
much is enough on a first pass.

| # | Chapter | Read it when you want to know |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | What runs and what talks to what, over which protocol and what happens when one end is missing — then why the layers are ordered as they are |
| 02 | [Domain model](02-domain-model.md) | What a quote, an assistant, an intervention and a planning run actually are, and every enum |
| 03 | [API reference](03-api-reference.md) | Which endpoint does what, and who is allowed to call it |
| 04 | [Quote lifecycle](04-quote-lifecycle.md) | How a quote gets written, approved, sent and accepted — and why refusal is not rejection |
| 05 | [Events and notifications](05-events-and-notifications.md) | What crosses RabbitMQ, how a notification reaches a browser, and what happens when the broker is down |
| 06 | [Planning computation](06-planning-computation.md) | How the solver turns accepted work into a calendar, and what it does when it cannot |
| 07 | [Front-end](07-frontend.md) | The screens, the routing, the state layers, the branding |
| 08 | [Configuration](08-configuration.md) | Every setting, every secret, and where each is read from |
| 09 | [Running and deploying](09-running-and-deploying.md) | The compose stacks, the images, and what production requires that development does not |
| 10 | [Testing](10-testing.md) | The three campaigns, what each covers, and how to run them |
| 11 | [Security](11-security.md) | Authentication, the role model, the row-level checks, and the known gaps |
| 12 | [Conventions](12-conventions.md) | The house style, and the rules a change is reviewed against |
| 13 | [Kubernetes](13-kubernetes.md) | How it scales, which autoscaler watches what, and the ceilings that were measured |
| 14 | [Observability](14-observability.md) | What it reports about itself, what is alerted on, and where LangChain will fit |
| 15 | [Electronic invoicing](15-electronic-invoicing.md) | What the French e-invoicing reform asks of this agency, why most of its revenue falls under e-reporting instead, and what has to change first, with the developer documentation of every approved platform worth calling — **design; the document builders are under way** |

---

## The system in one page

**A French home-care agency** sells hours of care at home — help washing,
preparing meals, cleaning, overnight sitting — and employs assistants who
deliver it. `SimpleERP` runs three things for that agency:

1. **Quoting.** A customer's needs become a quote of dated, timed, priced
   service lines. Prices come from a catalog, with surcharges for Sundays and
   public holidays, and VAT at either 5.5 % or 20 % depending on whether the
   service is a necessity or a comfort.

2. **Validation.** An assistant sitting with a family can write a quote, but
   does not set the agency's prices. What they write waits in a queue until a
   manager approves it, and the record says who approved it.

3. **Planning.** Every accepted quote line becomes a requirement — this service,
   for this customer, on this day, in this window. A CP-SAT solver assigns them
   to assistants and places them in time, respecting travel between addresses, a
   lunch break, declared absences, and a maximum radius from an assistant's home.

Around those three sit the supporting parts: accounts and roles, a workforce
with photographs and qualifications, a customer book, an event broker, a
notification stream, and outbound email carrying spreadsheets.

## The five decisions worth knowing up front

These come up repeatedly, and each is explained where it belongs.

- **A partial plan is refused, not stored.** A calendar missing three visits
  still looks like a calendar, and the visits quietly dropped are the ones that
  end with somebody waiting at their door. A run that cannot place everything
  fails, leaving last week's working plan alone, and its message names each
  unplaced visit and why. → [06](06-planning-computation.md)

- **Refusal is not rejection.** A manager sending a quote back means the agency
  will not make that offer; `REJECTED` means the family declined. They are
  opposite facts about the same customer, so a refused quote returns to `DRAFT`.
  → [04](04-quote-lifecycle.md)

- **A notification is a record, not a delivery.** It is written to the database
  first and pushed over SSE second, so a reader who was offline still finds it.
  A dropped frame costs latency, never the notification. →
  [05](05-events-and-notifications.md)

- **The broker being down never fails a request.** A quote is submitted whether
  or not the event could be published; the manager's queue is a database query,
  not a message. → [05](05-events-and-notifications.md)

- **Row-level checks live in the service, not the route.** A guard proves the
  caller is *an* assistant; only a comparison against the stored record stops
  assistant A reading assistant B's diary. → [11](11-security.md)

## Where things are

| Looking for | Go to |
|---|---|
| A domain model | `backend/models/src/models/<area>/` |
| A database table | `backend/storage/src/storage/orm/` |
| A migration | `backend/conf/alembic/versions/` |
| Business logic | `backend/service/src/service/<area>/` |
| An endpoint | `backend/api/src/api/v1/<area>/` |
| A screen | `frontend/src/features/<area>/` |
| Configuration | `backend/conf/app*.yaml` |
| A GUI test | `qa/robot/suites/` |
