# 12 — Conventions

The house style. A change is reviewed against this, and most of it is enforced
by ruff.

## Python

**Every module** begins `from __future__ import annotations`, then imports under
literal banner comments:

```python
from __future__ import annotations

# Standard library imports
from typing import List, Optional

# Third-party imports
from pydantic import BaseModel

# First-party imports
from models.enums import QuoteStatus
```

**Typing is deliberately pre-PEP-585/604.** `typing.Dict`, `List`, `Optional[X]`,
`Union[A, B]` — never `dict[...]` or `X | None`. Four ruff rules that would
rewrite it (`UP006`, `UP007`, `UP035`, `UP045`) are disabled *by design, not by
neglect*, and the pyproject says so.

**Google-style docstrings on every module, class, method and test**, with
`Args` / `Returns` / `Raises` / `Notes`. Class docstrings carry an `Attributes`
block.

The `Notes` sections are the signature of this codebase. They explain **why**,
and specifically why the obvious alternative is wrong. A comment restating what
the line does is noise; a note saying "asserting immediately would fail on a slow
machine and pass on a fast one" is the reason somebody does not undo the work
next month.

**Method-group banners** inside classes:

```python
    ############################
    # Internal Helpers Methods #
    ############################

    ############################
    # Publicly Exposed Methods #
    ############################
```

**One class per file** — models, rows, mappers, repositories, services. Exception
modules are the exception: a base `MTInvalid<Thing>Exception` and its subclasses
live together.

**A new entity gets a package, not a file.** Domain models live in
`models/<domain>/<aggregate>/`, with the entity, anything that only exists as
part of it, and an `exceptions/` package. Add the class to the aggregate's
`__init__.py` so callers import `from models.people.hca import Hca` and never
need to know which file it sits in — but import exceptions from the explicit
`models.people.hca.exceptions`, because a model reaching for its own package is
a cycle.

**The storage tree mirrors the models tree.** A row goes in
`storage/orm/<domain>/`, its mapper in `storage/mappers/<domain>/`, its
repository in `storage/repositories/<domain>/`, under the same domain name the
model uses. Changing an entity touches all three; finding them the same way each
time is what stops the third being forgotten. Add the row to
`storage/orm/__init__.py` as well — Alembic and the test schema builder read
every table through it, and one that nothing imports is a table `create_all`
silently omits. → [01](01-architecture.md)

**Shared fields live on a base in `models/base/`, and the exception stays per
model.** Every record describing a human extends `Person`; the two that carry a
photograph also mix in `PortraitHolder`. A new people model inherits both rather
than restating eight fields and seven validators — that is what the base is for,
and four hand-copied versions of "an email must be a non-empty string" is what it
replaced.

The rule the base holds raises `cls.INVALID_*`, and each subclass declares which
exception that is:

```python
class Customer(Person):
    INVALID_EMAIL: ClassVar[Type[MTInvalidPersonException]] = MTCustomerInvalidEmail
```

Pydantic binds `cls` to the concrete subclass, so a `Customer` still raises
`MTCustomerInvalidEmail` and an `Hca` still raises `MTHcaInvalidEmail`. **Do not
collapse them into one shared exception**: `api/exception_handlers.py` is keyed
on those classes, and one class would answer every model's malformed field with
the same status. The base's `MTPerson*` defaults exist only so a model that has
not declared its own still raises something typed rather than reaching the
catch-all as a 500.

A subclass that genuinely needs different behaviour **overrides the validator and
says why in its `Notes`** — `HcaApplication` lower-cases the email because it
becomes a sign-in; `User` does the same and relaxes `first_name` because a
service account is a mononym. An override must reuse the base's **method name**:
a differently-named validator on the same field stacks on top of the inherited
one rather than replacing it, and the two then run in an order nobody reading
either can predict.

**One service per entity.** The planning service absorbed the settings service
and the feasibility checker for this reason; the mapper package did the same.

**Exceptions are `MT`-prefixed** and domain-scoped: `MTQuoteNotEditable`,
`MTAuthInvalidCredentials`, `MTS3PayloadTooLarge`. A service raises its own; the
endpoint raises nothing. Translation happens once, in
`api/exception_handlers.py`, and `tests/api/test_exception_coverage.py` fails if
a family has no row.

**Logging** — every service and repository takes
`logger: Optional[Logger] = None`. `%s` lazy formatting, messages end with a full
stop, and a class covers DEBUG through ERROR. Secrets are never logged.

**No `Any`, and no `Dict[str, Any]` out of a public method.** Use
`pydantic.JsonValue` or return a model.

Line length 88; `# noqa` carries a reason.

## TypeScript

`strict`, plus `noUnusedLocals`, `noUnusedParameters` and
`noUncheckedIndexedAccess`. Absolute imports through `@/` — a relative chain like
`../../../shared/api` is the first thing to rot when a file moves.

TSDoc on every exported function and component, with the same `@remarks` habit
of explaining why.

Every element the GUI campaign touches carries a `data-testid`. A CSS class is
Emotion's to rename and a visible string changes with the copy; neither is a
contract.

One feature per directory under `src/features/`. Server state belongs to
TanStack Query and nowhere else — the Zustand store holds the session, and
nothing else.

## Robot Framework

Suites numbered in the order they run. Every locator a `data-testid`. Fixtures
created and torn down **through the API**, never by clicking. Anything created
carries a unique suffix; teardown removes exactly what that run made, by
identifier. Seeded data is read-only, or snapshotted and restored.

Suite documentation says what the suite proves and why it is worth proving.

## Migrations

Numbered `NNNN_short_name.py`, linear, with a module docstring explaining what
arrived together and why. A downgrade that would lose data says what it does
about it — 0006 moves pending quotes back to draft before narrowing the column.

## Commits and reviews

Not a git repository yet, so there is no commit convention to state. When there
is one, the reviewable unit is a vertical slice: model, row, mapper, repository,
service, endpoint and tests together.

Before proposing a change as finished:

```sh
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build
```

## The rule behind the rules

Most of the conventions here exist because somebody could not tell, six months
later, whether a line was deliberate. When you make a decision the next reader
would find surprising — a broad `except`, a status that is not the obvious one,
a check placed in an unexpected layer — write down what the alternative was and
why it was worse. That is what the `Notes` sections are for, and it is the one
convention worth keeping if every other were dropped.


## A formatter that corrupts source

`ruff` is capped **below 0.15** in `backend/pyproject.toml`, and the cap is not
housekeeping. From 0.15 onwards `ruff format` rewrites

```python
        except (InvalidOperation, ValueError):
```

into `except InvalidOperation, ValueError:` — Python 2 syntax, and a
`SyntaxError` on 3.14 — for handlers at method depth. It corrupted nine files
here in a single run.

**The dangerous part is not the corruption; it is that the test suite stayed
green.** CPython kept importing those modules from the `.pyc` files compiled
from the previous, correct source, so every test passed against bytecode whose
source no longer parsed. The damage would have surfaced on the next clean
checkout — in CI, or on somebody else's machine — with nothing pointing back at
the formatter run that caused it.

`tests/test_sources_are_parseable.py` is the backstop: it parses every file in
the workspace from its own bytes, and `ast.parse` never consults the bytecode
cache. If the cap is ever lifted, that test is what will say so.

Bisected: 0.14.0 clean, 0.15.4 and 0.16.1 corrupt.
