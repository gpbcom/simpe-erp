# 15 — Electronic invoicing (facturation électronique)

> **Status: design, with the platform-independent slices under way.** The
> chapter was written to settle the decisions before any code existed, because
> the reform reaches into the model, the renderer, the object store and the
> invoice lifecycle at once — four places that are expensive to change twice.
> Slice 5's document builder — `FacturXBuilder` — and
> the recipient migration exist, and **slice 6 is now built**: connectors for
> all four documented platforms under `backend/integrations/connectors/`, an
> encrypted credential store, a gallery to connect one, and automatic
> transmission when a bill is marked paid. What remains unbuilt is slice 7's
> periodic e-reporting *aggregates* — the per-invoice payment declaration is
> wired. Read §*The work, in order* for which is which, and treat any conflict
> between this chapter and the code as the chapter being behind.
>
> **The regulation is a moving target and this chapter is a snapshot.** The
> calendar has already slipped twice and the free public exchange service was
> withdrawn after the first design was published. Every date and every
> obligation below must be re-checked against `impots.gouv.fr` and against the
> chosen platform's own specification before a line is committed to it.

## Why this is not "add an XML export"

The reform replaces a *document sent to a customer* with a *structured message
routed through a certified intermediary, whose lifecycle the tax authority
watches*. Three consequences fall out of that sentence, and each one is a change
this codebase does not currently have room for:

- an invoice acquires a **recipient who is not the person cared for**;
- an invoice acquires **states nobody in the agency decides** — a platform or a
  customer rejects it, and the record has to accept that;
- some invoices stop being invoices at all and become **reported data**.

## The two obligations, and which one applies to whom

The reform is two regimes wearing one name. Confusing them is the most expensive
mistake available here, because they have different scopes, different payloads
and different destinations.

| | **e-invoicing** | **e-reporting** |
|---|---|---|
| Applies to | domestic B2B, both parties VAT-registered | B2C, international, and **payment data** |
| What is transmitted | the whole invoice, structured | transaction data, aggregated |
| Reaches | the buyer, via a platform | the tax authority only |
| The customer receives | a structured invoice | whatever you already send them |

Mapped onto what this agency actually invoices:

| Flow | Who is billed | Regime | State today |
|---|---|---|---|
| Care sold to a household | a private individual | **e-reporting** — transaction *and* payment data | `Bill` handles it |
| APA, aide sociale | conseil départemental, CCAS | **B2G — Chorus Pro**, mandatory since 2020 | **not handled at all** |
| Complementary cover | mutuelle, caisse de retraite | **e-invoicing** (B2B) | not handled |
| Employer-funded care | comité d'entreprise, employer | **e-invoicing** (B2B) | not handled |

**Most of the revenue is B2C, and B2C is not electronic invoicing.** The
household's invoice does not have to become a Factur-X file addressed to
anybody. What has to happen is that the agency reports the transaction, and —
because this is a supply of *services*, where VAT falls due on collection rather
than on delivery — also reports **when it was paid**.

The B2G line is the uncomfortable one. If the agency invoices a conseil
départemental for APA, that obligation is not coming in 2026; it arrived in
2020. It should be checked before anything in this chapter is scheduled.

## The calendar

The agency is a PME/TPE, which decides everything:

| Date | Obligation | Does it touch SimpleERP? |
|---|---|---|
| **1 Sep 2026** | every company must be able to **receive** an electronic invoice, and be reachable through the directory | **No.** This is the purchase side. It needs a platform contract, not a feature. |
| **1 Sep 2027** | PME/TPE must **issue** electronic invoices and perform **e-reporting** | **Yes.** Everything below. |

A decree may push each date back by one quarter, to 1 December. Planning to the
December date would be planning to the optimistic reading of a calendar that has
already moved twice against the people who did that.

So: **2026 is a procurement year, 2027 is the delivery year** — with one
exception, Chorus Pro, which is already late.

## The decision that is not a development decision

The original architecture offered a free public exchange service. **It was
withdrawn**: the public portal keeps the directory and the concentration of data
for the administration, and no longer exchanges invoices. Every issuer must
contract with a **certified platform**.

That choice is a prerequisite for the code, not a consequence of it, because it
fixes:

- the **API** the connector speaks — every platform publishes its own, there is
  no standard client;
- **which formats** are accepted on input, and therefore whether the renderer
  must produce PDF/A-3 or may hand over XML alone;
- **how lifecycle statuses come back** — webhook, polling, or a file drop — and
  a webhook is the only one of the three this codebase already has the shape
  for;
- **who archives**, and for how long, which decides whether §*Archiving* below
  is our problem or a line in a contract.

Nothing in this chapter should be built before that contract is signed, except
the parts marked **platform-independent**.

## The platforms, and their developer documentation

> Researched August 2026 against each vendor's own documentation. Everything
> below is a **snapshot of a market that is still forming** — endpoints,
> pricing and registration status all move. Treat the URLs as the durable part
> and the details as something to re-read before signing.

### What the official list is, and what it does not say

The DGFiP publishes the register on `impots.gouv.fr`, mirrored as an open
dataset on `data.gouv.fr`. It comes in two parts, and the difference matters:

- **immatriculée définitivement** — the audit report has been delivered;
- **immatriculée sous réserve** — the dossier passed the first instruction
  phase and the platform holds a number, but the **audit report is still
  outstanding**.

`docs/liste_pa_attente_rapport_audit.pdf` in this repository is the *second*
list: **145 platforms awaiting their audit report**. Every candidate below is
on it. So "immatriculée" on a vendor's home page is not the same claim as
"certified", and §*What to verify before building* item 3 should be read as
including the registration *status*, not only the number.

Note also that the reform renamed the category. **PDP** (*plateforme de
dématérialisation partenaire*) and **PA** (*plateforme agréée*) are the same
thing; vendor sites use both, often on the same page.

### The filter this agency applies

The obvious search — "who has an API for sending an invoice?" — is the wrong
one here, and §*The two obligations* is why. **Most of the revenue is B2C**,
and B2C never produces an invoice for a platform to route. What it produces is
e-reporting, and specifically two of the DGFiP's numbered flows:

| Flux | Carries | Why this agency needs it |
|---|---|---|
| 10.1 / 10.2 | international B2B transaction data | rarely, if ever |
| **10.3** | **B2C transaction data** | the bulk of what the agency invoices |
| **10.4** | **payment data (encaissement)** | VAT on services falls due on collection |

A platform with a beautiful B2B invoice API and no flux 10.3/10.4 is useless
here. Add **Chorus Pro** for the APA/conseil départemental flow — already five
years late — and the filter is three-way: e-reporting, B2G routing, and only
then B2B e-invoicing.

One more criterion comes from this codebase rather than from the reform.
§*The decision that is not a development decision* notes that of webhook,
polling and file drop, **a webhook is the only one this repository already has
the shape for** — the loopback callbacks behind planning-completed and
bill-accepted. A platform that returns lifecycle statuses by webhook costs a
handler; one that only offers polling costs a scheduled job that does not
exist yet.

### The four that publish real developer documentation

Of the 145, roughly a dozen publish documentation a developer can read without
signing anything. Four of those clear the filter above.

#### B2BRouter

Spanish, ISO 27001, Peppol access point, registered 12/12/25 (p.1 of the list).

| | |
|---|---|
| Guides | `https://docs.b2brouter.net` |
| API reference | `https://developer.b2brouter.net/reference` |
| Machine-readable index | `https://developer.b2brouter.net/llms.txt` — every page as Markdown, endpoints as OpenAPI |
| Staging base URL | `https://api-staging.b2brouter.net` |
| Auth | headers `X-B2B-API-Key` and `X-B2B-API-Version` |
| SDK | PHP, `github.com/B2Brouter/b2brouter-php` |

The send flow, end to end:

```
GET  /directory/{country}/{identifier}          # is the recipient reachable?
GET  /accounts/{ACCOUNT_ID}/contacts            # or list what exists
POST /accounts/{ACCOUNT_ID}/contacts            # → CONTACT_ID
POST /accounts/{ACCOUNT_ID}/invoices            # JSON body → INVOICE_ID
POST /accounts/{ACCOUNT_ID}/invoices/import     # …or octet-stream XML
POST /invoices/send_invoice/{INVOICE_ID}
GET  /invoices/{INVOICE_ID}?include=lines
```

`send_after_import` (query parameter on import, field on create) decides
whether creating also transmits. **Leave it false.** Creating and sending in
one call means a malformed payload and a transmitted invoice are the same
request, and §*Factur-X* is explicit that a rejected document has already
consumed a number from a series that cannot have gaps.

Formats: 22+, including Factur-X/ZUGFeRD, UBL, CII, EDIFACT, FatturaPA and
XRechnung, converted between on the way through. Networks: **Chorus Pro** and
FACe for public bodies, Peppol, SDI, ESPAP. Webhooks are documented; a sandbox
runs on the same base URL under a test key, which is worth noting — there is no
separate host to configure, only a different secret.

**Why it is on the shortlist:** the only candidate with *both* documented
webhooks and explicit Chorus Pro routing, which is exactly this agency's two
awkward requirements.

#### Storecove

Dutch, API-first, sold to software publishers. Registered 28/04/26 (p.4).

| | |
|---|---|
| Docs | `https://www.storecove.com/docs` — open, no login |
| Base URL | `https://api.storecove.com/api/v2/` |
| Auth | `Authorization: Bearer <API_KEY>` |
| Submit | `POST /document_submissions` → returns a GUID |

The body is a `SendableDocument`: `routing` (Peppol `eIdentifiers` and/or
email addresses), `invoice` (parties, lines, totals, taxes), and
`consumerTaxMode`. **The API takes structured JSON and produces the country's
format itself** — for France, Factur-X.

Statuses come back either way round, which is unusually accommodating:

- **push** — Storecove `POST`s to a URL you register, protected by HTTP Basic
  or a custom header, expecting `200`, retrying for **five days**;
- **pull** — `GET /webhook_instances` drains a FIFO queue, `DELETE` per event
  once processed, `204` when empty.

The sandbox simulates the exchange networks and tax authorities themselves —
OpenPeppol, SDI, KSeF, FACe, eSPap — with published test identifiers.

**One integration constraint worth knowing before choosing it:** legal
entities and their identifiers are created in the web console at
`app.storecove.com/senders`, **not through the API**. You get a
`legalEntityId` back and every submission references it. For a single-tenant
agency that is a one-off setup step; for a multi-company deployment it is
manual work per company, and this application is multi-tenant by
`company_id`.

The French e-reporting endpoints are the least documented part of an otherwise
excellent reference, and Chorus Pro is not mentioned at all. For an obligation
that has been mandatory since 2020, absence of documentation is a question to
ask them, not a gap to assume.

#### Invopop

Spanish, developer-first, built around an open format. Registered 15/01/26 (p.2).

| | |
|---|---|
| Docs | `https://docs.invopop.com` |
| French guide | `https://docs.invopop.com/guides/fr-pa` |
| Machine-readable index | `https://docs.invopop.com/llms.txt` |
| Auth | API key from the console; application credentials carry an owner id |

The API is five services rather than one surface:

| Service | OpenAPI | What it holds |
|---|---|---|
| **Silo** | `silo_v1` | document entries (create/fetch/update/search), file upload and attach, GOBL build / sign / correct |
| **Transform** | `transform_v1` | workflows, and jobs that execute them |
| **Sequences** | `sequence_v1` | series and numbering |
| **Access** | `access_v1` | workspaces and enrolment |
| Utils | — | helpers |

Invoices are written in **GOBL** (*Go Business Language*) — an open-source
JSON-Schema format with its own tax-rule database, at
`github.com/invopop/gobl`. It is genuinely open, and usable to model and
validate an invoice whether or not you ever send it through Invopop.

The French coverage is the most explicitly documented of the four:

| Flow | Flux | Supported |
|---|---|---|
| Domestic B2B e-invoicing | 2 & 6 | yes |
| International B2B reporting | 10.1–10.2 | yes |
| **B2C transaction data** | **10.3** | **yes** |
| **Payment data** | **10.4** | **yes** |
| B2G via Chorus Pro | — | yes, as a separate integration |

"A single GOBL invoice can generate and send any of the formats allowed in
France (UBL, CII, Factur-X)", with a *PDF Generator* app for the
human-readable half. A sandbox exists with a documented "from sandbox to live"
path. What the French guide does **not** state is whether statuses return by
webhook or polling — there is a webhooks guide elsewhere in the docs, but the
French flows are described as GOBL documents exchanged between platforms over
Peppol without naming the callback mechanism. Worth confirming, given the
criterion above.

#### Iopole

French, and the only candidate of the four that is. PA n°0018, registered
11/12/25 (p.2). SecNumCloud hosting, ISO 27001, a stated 99.9% SLA.

| | |
|---|---|
| API reference | `https://docs.iopole.com` |
| Developer portal | `https://www.iopole.com/en/developpeurs` |
| Sandbox | free, private, self-served |
| Rate limit | 3,600 requests/minute per source IP, enforced at TCP level |

**The API is asynchronous by design.** Most state-changing calls return a
`guid` immediately, and each endpoint's description says whether it is async;
the guid is how you later ask what happened. That is a different integration
shape from B2BRouter's synchronous create-then-send, and it means the
connector needs somewhere to keep a correlation id — which
`InvoiceTransmission.platform_message_id` in §*Transmission is not a property
of the invoice* already is, before anybody knew which platform it was for.

Formats UBL / CII / Factur-X, built through their API, plus directory lookup
against the PPF. E-reporting is documented as **flux 10.1 to 10.4** and sold
explicitly at software publishers rather than at end users.

**Caveat on this entry.** Iopole's web servers return malformed HTTP headers
and their documentation site renders client-side, so — unlike the other three
— none of the above was read directly from the source. It is assembled from
search indexing of their own pages, and every line of it should be re-verified
against `docs.iopole.com` in a browser before it decides anything.

### Also registered, and worth knowing about

Not shortlisted, but on the list and likely to come up:

| Platform | List | Note |
|---|---|---|
| **Super PDP** (p.4) | 22/12/25 | ISO 27001, Peppol AP/SMP, **free up to 1 000 invoices/month**, then €0.0025–0.01 per invoice. Cheapest by a distance at this agency's volume. API documentation is referenced but not openly linked. |
| **Seqino** (p.3) | 15/01/26 | REST with multi-language SDKs and a sandbox, SecNumCloud, white-label. Pricing on quote only. |
| **Pennylane** (p.3) | 11/12/25 | Public "API Entreprise V2", `POST /e-invoice-import` accepts a Factur-X PDF. An accounting product first — relevant if the agency's accountant already uses it. |
| **Tenor** (p.4) | 15/01/26 | French, described as API-first middleware for ERP connections. |
| Cegid, Sage, Odoo, Qonto, Sellsy, Axonaut, Esker, Generix, Edicom, Basware, Comarch, Pagero, Sovos, Avalara, Tradeshift | various | All registered. All are products the agency would be *adopting*, not APIs it would be *calling* — except Edicom, Esker and Generix, which are EDI houses whose integration is a project rather than a client library. |

**`FactPulse` is not on this list.** French comparison sites name it repeatedly
as an API-first PA; whatever its status, it is not among the 145 awaiting
audit, so it is either fully immatriculated or not registered. Check before
believing either.

### What this changes about the work

**Every one of the four builds the structured format from JSON.** Read
carelessly, that says `FacturXBuilder` was wasted
work. It was not, and the reason is in its own docstring:
*"what the reform adds on top — routing, lifecycle, transmission — is not in
this file at all; it belongs to the platform."*

Each candidate offers **two doors**, and they are a real architectural choice:

| | Submit structured JSON | Import a built file |
|---|---|---|
| Who writes the EN 16931 document | the platform | us, from `Bill` |
| B2BRouter | `POST /accounts/{id}/invoices` | `POST /accounts/{id}/invoices/import` |
| What we owe them | our model re-encoded into their JSON | an octet-stream |
| Cost of switching platform | remap every field | change a base URL |
| Who to blame for a rejected document | them | us |

The import door is the better fit **because the builder already exists**.
Re-encoding `Bill` and `BillLine` into a vendor's JSON shape would be a second
mapping of the same data, competing with the CII one, and it would put the
invoice's legal content inside somebody else's schema — which is precisely
what §*Transmission is not a property of the invoice* separates. Submitting
JSON also makes the platform, not this repository, the thing that decides what
the customer's invoice says.

Two consequences worth recording:

1. **The PDF/A-3 gap has a second exit.** `FacturXBuilder` documents that it
   stops short of archival-grade PDF/A-3 for want of an ICC output intent.
   Platforms that generate the document produce a conforming one, so the gap
   can be closed by *not* being the one who assembles it — at the price of the
   first column above. Decide it with a validator, as §*Factur-X* already
   insists, not on this table.
2. **`backend/integrations/connectors/` is where the connector goes**, and it is
   an empty package today. Keeping it outside `service/` is right: the
   platform client is I/O against a third party, versioned by them, and the one
   part of this chapter that a change of supplier should be able to replace
   without touching a domain rule.

### What could not be verified

Recorded so the next person does not re-run the same searches:

- **Iopole**: nothing read from source — malformed HTTP headers on
  `iopole.com`, client-side rendering on `docs.iopole.com`. Needs a browser.
- **Invopop**: whether French lifecycle statuses arrive by webhook or must be
  polled. Not stated in the French guide.
- **Storecove**: Chorus Pro / B2G, absent from the documentation entirely.
- **Super PDP, Seqino**: API documentation referenced by both, openly linked by
  neither. Both would need a sales conversation to evaluate, which is a fact
  about them worth weighing.
- **Nobody's pricing at this agency's volume**, except Super PDP's published
  tiers. A few hundred invoices a month is small enough that per-invoice
  pricing and a flat subscription differ by an order of magnitude.

## What the current model cannot express

### One invoice, one recipient

`Bill` carries `customer_id`, `customer_full_name` and `customer_address`, and
nothing else. The recipient *is* the person cared for.

That is false for every funded flow, and it is false in a specific way that
matters: an APA arrangement is **one course of care, split between two payers**.
The département pays its share, the household pays the *reste à charge*. Today
this can only be modelled as two unrelated invoices whose relationship exists
nowhere — with two numbers out of one series, and no way to answer "what did
this month of care cost, and who paid which part".

**This is the deepest change in the chapter**, and it is worth doing before the
reform rather than because of it.

### No identifiers for anybody but the agency

`Company` carries SIRET, VAT number, RCS and share capital. `Customer` carries a
name and an address, which is all a household has and all it needs.

A funded recipient needs a **SIREN** — and for a public body, a **service code**
in addition, because a département routes by service. Neither has anywhere to
live.

### No nature of operation

The reform requires an invoice to state whether it covers a supply of goods, a
supply of services, or both. Everything this agency sells is services, so the
value is constant — which is an argument for a default, not for the field's
absence. A stored constant survives the day the agency starts selling equipment;
an implicit one does not.

### A lifecycle that only moves when the agency moves it

`BillStatus.can_move_to` allows exactly one step, forwards or back. It was
written for a lifecycle in which every transition is a manager's decision, and
it is correct for that.

The reform adds transitions **nobody here decides**: a platform refuses a
malformed invoice, a buyer rejects one they dispute. Those arrive
asynchronously, they are not adjacent to the current state, and refusing them
because they skip a step would mean the record disagrees with the tax
authority's copy.

## The shape to build

### Transmission is not a property of the invoice

The temptation is to add `transmission_status`, `transmitted_at`,
`platform_message_id` to `Bill` and be done in an afternoon.

**That is the wrong home, for the reason `Bill` already stores its totals rather
than computing them**: an invoice is a legal document that must reprint
identically for ten years. Its record should change as little as possible after
issue. A transmission, by contrast, changes many times — submitted, accepted by
the platform, delivered, rejected, resubmitted after correction — and each
change would be a write to a row that is supposed to be settled.

So: a separate aggregate, one per attempt.

```
Bill ──1─────*── InvoiceTransmission
 │                    │
 │                    ├── channel        (platform | chorus-pro | e-reporting)
 │                    ├── format         (factur-x | ubl | cii)
 │                    ├── status         (queued … accepted | rejected)
 │                    ├── platform_message_id
 │                    ├── submitted_at, settled_at
 │                    └── failure_reason
 │
 └── recipient (new) ─── the party that owes the money
```

`Bill.status` keeps meaning what it means today — where the invoice stands
**commercially** — and gains nothing. Where it stands *technically* is a
question about the transmission, and asking it of the invoice is what would make
"waiting payment" mean two unrelated things: exactly the confusion
`BillStatus`'s own docstring already refuses for generation failures.

### The recipient

A minimal shape that covers all four flows:

| Field | Household | Public body | Company |
|---|---|---|---|
| `kind` | `individual` | `public` | `business` |
| `name` | the customer's | the département's | the mutuelle's |
| `address` | the customer's | its billing address | its billing address |
| `siren` | — | required | required |
| `service_code` | — | required (Chorus Pro routing) | — |
| `vat_number` | — | usually absent | required if VAT-registered |
| `share` | the *reste à charge* | its funded share | its funded share |

The **share** is what makes an APA split expressible without inventing a second
invoice. Whether a split produces one invoice with two recipients or two
invoices linked by a common reference is the one modelling question this chapter
does not settle — it depends on what the département's own system expects, which
is a question for them and not for us.

### The lifecycle, extended

Regulatory statuses, and what they mean here:

| Status | Set by | Maps to |
|---|---|---|
| **déposée** | us, on submission | `InvoiceTransmission.SUBMITTED` |
| **rejetée** | the platform | `InvoiceTransmission.REJECTED` — a format or routing fault, ours to fix |
| **refusée** | the buyer | a commercial dispute — belongs on `Bill`, not on the transmission |
| **encaissée** | us, on payment | `BillStatus.PAID`, **which already exists** |

`encaissée` is mandatory for services, and it is the one the agency already
records: moving a bill to `PAID` is precisely the event the tax authority wants
reported. That is a rare piece of luck — the existing lifecycle's last step is
already the regulatory one, and it only needs to *publish*.

`refusée` is the transition that breaks `can_move_to`. It arrives from outside
and it is not adjacent to anything. The rule should not be loosened for it;
refusal is a *different kind of event* from a manager stepping the invoice
along, and folding it into the same method would remove the guard that stops a
misclick jumping to paid. A named transition — the precedent is
`CustomerService.promote` sitting beside `set_status` — keeps both facts.

## Factur-X, and why the PDF is the hard part

Factur-X is a **PDF/A-3 carrying an embedded CII XML attachment**. Human-readable
and machine-readable in one file, which is why it is the natural target here: the
household still gets something it can read, and a funded payer gets structure.

The XML is the easy half. The mandatory data — number, dates, agency identity,
VAT split by rate, per-line amounts — is **already on `Bill` and `BillLine`**,
because a conforming French paper invoice and the EN 16931 core model want
nearly the same things. The mapping to check:

| EN 16931 | Source today |
|---|---|
| BT-1 invoice number | `Bill.number` |
| BT-2 issue date | `Bill.issued_on` |
| BT-3 type code | constant `380`; `381` for a credit note **that does not exist yet** |
| BT-9 due date | `Bill.due_on` |
| BT-27 / BT-30 / BT-31 seller name, SIREN, VAT | `Company` |
| BT-44 / BT-47 / BT-48 buyer name, SIREN, VAT | **the new recipient** |
| BT-70…75 deliver-to party and address | `Customer.address` — the care is delivered to the household even when a payer is billed |
| BG-23 VAT breakdown | `Bill.vat_by_rate()` |
| BT-109 / BT-110 / BT-112 totals | `Bill.total_ht` / `total_vat` / `total_ttc` |
| BT-153 / BT-129 / BT-146 line item, quantity, unit price | `BillLine` |

### What was built, and how it is checked

The **post-process** route was taken: `InvoiceRenderer` still lays the page out,
`FacturXBuilder` writes the structured file from the same `Bill` and attaches
the second to the first. One object under one key —
a generation run now stores a Factur-X document rather than a plain PDF, and the
existing download endpoint serves it unchanged.

Three things make that more than an assertion:

- **The builder validates its own output** against the official schema on every
  call and raises rather than returning. The schema is what fixes the *element
  order*, and the order in the builder is the order of its method calls — so a
  refactor that moves two lines produces a file that reads perfectly and no
  platform accepts. A test proves the check is live by subclassing the builder
  to emit one line's elements the wrong way round.
- **Every font is embedded.** ReportLab's built-in faces are named, not carried,
  which an archival format forbids: a document that renders differently in ten
  years is not a copy of what the customer was sent. The renderer now registers
  the TrueType faces that ship *inside ReportLab*, so nothing was added to the
  repository and no system font is depended on. Asserted by reading the font
  descriptors back out of the produced file.
- **The two halves cannot disagree**, because they are built from one `Bill` in
  one call. A test extracts the XML back out of the assembled document and
  compares it byte for byte with a freshly built one.

### The two gaps, named rather than papered over

**The output intent is missing, so the document is not archival-grade PDF/A-3.**
Everything else the profile asks for is there — the attachment and its
relationship, the XMP declaring both the PDF/A part and the Factur-X extension
schema, the embedded fonts — but a conforming file must also carry an output
intent naming an ICC colour profile, and that is a binary asset this repository
does not ship and could not vet. The fix is small and known: add an sRGB profile
and write the output intent. It is a licensing and provenance decision, not a
programming one, which is why it was not made here.

**The business-rule check is not running, and reporting it as green would be
worse than not running it.** The European rules that check the totals add up and
that every mandatory term is present live in a Schematron requiring an XSLT 2.0
engine — in practice a Saxon service on `localhost:5000`, which this deployment
does not run. Called without one, the reference library **returns success
without checking anything**; that was verified by feeding it an invoice with a
deliberately wrong grand total, which it accepted. So it is not called at all.

What stands in for it is narrower but real: the schema check above, and
`Bill.check_totals`, which refuses to *construct* an invoice whose totals
disagree with its lines. The arithmetic rules are therefore unreachable rather
than unchecked. What remains genuinely unverified is the rest of the rule set —
including the French CTC profile the library also ships. Running a Saxon
container in the test campaign would close it.

## E-reporting: the part most of the money goes through

For the B2C flows, no Factur-X leaves the building. Instead, two periodic
transmissions:

- **transaction data** — the aggregate of what was invoiced to individuals over
  a period, by VAT rate;
- **payment data** — when those invoices were collected, because VAT on services
  falls due on collection.

Both are derivable from what is already stored: `Bill` rows filtered to
individual recipients, grouped by `vat_by_rate()`, and — for payments —
`BillStatus.PAID` with its date. **No new source of truth is needed**, which is
the single most encouraging fact in this chapter.

The transmission frequency depends on the VAT regime and must be read off the
agency's own filing obligation rather than configured to a guess.

**Where it runs:** the existing `billing` worker role, not a fifth one. That
role exists because generation is long, I/O-bound and spiky — a monthly close is
hundreds of renders and uploads. An e-reporting aggregate is the same shape on
the same cadence over the same data, and giving it its own deployment would buy
isolation from a queue it would never contend with.

## Archiving

Ten years, in a form that keeps its evidential value, with a *piste d'audit
fiable* linking the invoice to the care actually delivered.

The good news: the audit trail exists as data. A `BillLine` carries
`quote_line_id` and, where a visit was placed, `intervention_id` — the chain
from the sold service to the delivered visit to the charged line is already
recorded, and was designed to survive a replan deleting the intervention.

The gap is the object store: invoices are written under a private prefix with no
retention policy, no immutability and no versioning. Object-lock on the invoice
prefix is a configuration change, not a feature, and it should be made whatever
else is decided — a ten-year obligation guarded only by nobody having run a
delete is not a guarantee.

## The work, in order

| # | Slice | State | Depends on the platform? | Why here |
|---|---|---|---|---|
| 1 | **Mandatory mentions**: recipient SIREN, nature of operation | ✅ **built** | **No** | Required by the reform *and* useful on a paper invoice today. Nothing structured can be built until the data exists. The delivery address turned out to need no new field — the customer's address already *is* the deliver-to party. |
| 2 | **Recipient and payer share** — the model change | ✅ **built** (migration 0026) | **No** | The deepest change. Everything B2B and B2G is blocked on it, and it fixes an APA gap that predates the reform. The share is modelled and **refused by the structured builder** until the split shape is settled. |
| 3 | **Chorus Pro** for the départements | ❌ not started | No — Chorus Pro *is* the platform | Already mandatory. Ahead of the 2027 work, not behind it. |
| 4 | **Object-lock and retention** on the invoice prefix | ❌ not started | **No** | Configuration. Do it now. |
| 5 | **Factur-X**: CII XML + PDF/A-3 + validator in the test campaign | ⚠️ **built, with two gaps** | Partly — the profile is fixed by the platform | The long pole. The schema check and the embedded fonts are in; the output intent and the Schematron are not — see §*The two gaps*. |
| 6 | ~~**`InvoiceTransmission`** + the platform connector + inbound statuses~~ **Built** | **Yes** | Four connectors behind one `InvoicingConnector`; credentials sealed with Fernet; routed by `TransmissionKind.for_recipient`. Inbound statuses are still outstanding — what exists is the outbound half. |
| 7 | **E-reporting** aggregates, transaction and payment | **Yes** | Partly: flux 10.4 is declared per settled invoice as it happens. The *periodic aggregate* over a VAT window is not built. |

Slices 1, 2, 3 and 4 are worth doing on their own merits, whatever the reform
does next. That is deliberate: they are the ones a calendar slip cannot waste.

**Nothing in 1, 2 or 5 waits on the platform choice**, which is why they were
built first: a structured invoice is the same document whoever carries it, and
the parts that differ per platform — routing, lifecycle, transmission — are not
in the file at all.

## Deliberately out of scope

- **Receiving** invoices from suppliers. It is the 2026 obligation, and it is
  accounts payable — a different product, or a platform's own inbox.
- **Credit notes.** Already noted as absent when billing was built: French
  numbering forbids gaps and reuse, so a mistaken invoice is corrected by an
  *avoir*, not deleted. The reform makes this sharper — a rejected invoice
  cannot be edited and re-sent — so a credit note stops being optional at
  slice 6. It is a chapter of its own.
- **The attestation fiscale** for the crédit d'impôt (art. 199 sexdecies).
  Unaffected by the reform, and unbuilt.

## What to verify before building

1. The **company size category**, on paper. It decides 2026 against 2027, and
   this chapter assumes PME/TPE.
2. Whether a conseil départemental is invoiced today, and **how it is being done
   now** — that obligation is five years old.
3. The **platform**, with its API specification and its accepted Factur-X
   profile in hand — and its **registration status**, not merely its number:
   every candidate in §*The platforms* is on the *awaiting audit report* list.
   The open questions per candidate are listed there under §*What could not be
   verified*, and each is a question for a salesperson rather than a search
   engine.
4. The **e-reporting frequency** implied by the agency's VAT regime.
5. Whether an APA split should be **one invoice with two payers or two linked
   invoices**, asked of the département rather than decided here.
