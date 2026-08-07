# seed

Idempotent development data.

```sh
uv run seed
```

Run once by the development compose overlay after the migrations.

**Idempotent by identifier.** Every primary key is a UUID5 derived from a
natural key, so the seeder is an upsert: a second run writes nothing. That is
what lets it run on every `up` without anybody having to remember whether they
already did.

**Writes through the repositories, not raw SQL.** Seeded data should exercise
the same validation the application does, or it is exactly the fixture that
turns out to be impossible to create through the UI.

**Every address carries its coordinates.** `PostalAddress` geocodes during
validation, so seeding forty addresses without them would fire forty live
requests at Nominatim's public instance and get the machine's IP blocked.

Produces one Paris agency: 3 staff accounts, 12 assistants (and their accounts),
40 customers, 8 catalog entries, 54 quotes across every status, and next week's
service dates so a planning run has something to place.

Credentials are printed at the end of every run — `admin@simple-erp.fr`,
`manager@simple-erp.fr`, `firstname.lastname@simple-erp.fr`, all with
`simple-erp-demo-2026`.

One of those assistants — `marc.dubois@simple-erp.fr` — is seeded with the
**manager** role rather than the assistant one, so the agency has somebody who
manages *and* still covers rounds. Without them, no account held both a
manager's role and an assistant record, and the parts of the account page that
need both were unreachable.
