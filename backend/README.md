# rt-erp — backend

A `uv` workspace of six members, with a strict one-directional dependency graph.

```
models  ←  storage  ←  service  ←  api
                          ↑
                          ├──  worker
                          └──  seed
```

| Member | Holds |
|---|---|
| [`models`](models/README.md) | Domain models, configuration, enums, exceptions |
| [`storage`](storage/README.md) | ORM rows, mappers, repositories, migrations, object store |
| [`service`](service/README.md) | Business logic, the CP-SAT planner, messaging, email |
| [`api`](api/README.md) | FastAPI routers, middleware, dependency wiring |
| [`worker`](worker/README.md) | Broker consumer: runs solves, writes notifications |
| [`seed`](seed/README.md) | Idempotent development data |

## Running it

```sh
uv sync
alembic -c conf/alembic.ini upgrade head
uv run uvicorn api.main:app --reload      # or: uv run api
uv run worker                             # in another shell
uv run seed                               # once, to fill the database
```

Configuration is selected with `RT_ERP_CONFIG`, defaulting to `conf/app.yaml`.
→ [docs/08](../docs/08-configuration.md)

## Checks

```sh
uv run pytest                              # 938 tests, hermetic
uv run pytest -m integration               # needs the stack up
uv run ruff check . && uv run ruff format --check .
uv run ty check                            # see docs/10
```

## Conventions

`from __future__ import annotations` first; banner-commented import groups;
Google docstrings with a `Notes` section explaining *why*; one class per file;
`MT`-prefixed exceptions translated centrally; pre-PEP-585 typing, deliberately.
→ [docs/12](../docs/12-conventions.md)
