# storage

Everything that persists. Depends on `models`.

```
db/            async engine and the session context manager
orm/           SQLAlchemy rows — one class per table
mappers/       row ↔ domain model, both directions
repositories/  the query surface each service uses
s3/            assistant photographs
```

**A repository never commits.** It is handed a session already inside a
transaction, so a service performing several writes gets one transaction rather
than one per call.

**`BaseMapper` carries the machinery once.** A concrete mapper supplies only
`_build_model` and `_apply_fields` — the two directions that genuinely differ
per table. Insert and update share `_apply_fields`, which is what stops a column
being written on create and forgotten on update. Two class flags say whether the
model and the row carry timestamps, because not all of them do.

Read helpers swallow database errors, log at ERROR and return empty; write paths
let the error propagate so the transaction rolls back. Silently succeeding on a
failed write would be far worse than a failed request.

Migrations live in `../conf/alembic/versions/`, and
`tests/storage/test_migrations.py` fails on ORM drift.
