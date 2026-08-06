# models

Domain models, configuration and enums. **Depends on nothing first-party**, and
must stay that way — every other member imports it.

```
auth/  catalog/  companies/  configuration/  geo/  messaging/
notifications/  people/  planning/  quoting/  schemas/  settings/
enums.py
```

Everything is Pydantic with per-field validators raising its own `MT*` family.
Validation runs on the way **in and out** of the database, so a value that
stopped being valid is caught at the boundary.

`schemas/` holds the request and response models the API speaks — separate from
the domain models on purpose: a field added to `User` reaches the wire only if
somebody also adds it to `UserResponse`.

**One thing here touches the network.** `PostalAddress` geocodes against
Nominatim during validation. That is why the seeder supplies coordinates and why
the test suite neutralises it with an autouse fixture.

→ [docs/02](../../docs/02-domain-model.md), [docs/08](../../docs/08-configuration.md)
