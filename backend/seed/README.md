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

Credentials are printed at the end of every run — `admin@rt-erp.fr`,
`manager@rt-erp.fr`, `firstname.lastname@rt-erp.fr`, all with
`rt-erp-demo-2026`.
