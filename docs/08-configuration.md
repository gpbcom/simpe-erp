# 08 — Configuration

YAML for settings, environment variables for secrets, and nothing in between.

## The files

| File | Used by | Differs by |
|---|---|---|
| `backend/conf/app.yaml` | a process run on the host | `localhost` addresses; broker and email **off** |
| `backend/conf/app.dev.yaml` | the development compose overlay | container addresses; email **on**, pointed at Mailpit |
| `backend/conf/app.docker.yaml` | the base and production stacks | container addresses; broker **on**, email off |

Selected with `RT_ERP_CONFIG`. `AppConfig.load()` resolves it relative to the
working directory, then relative to `backend/`, then falls back to
`conf/app.yaml`.

Alembic loads the same file, deliberately — so migrations and the application
can never disagree about which database they mean.

## The sections

| Section | Holds |
|---|---|
| `server` | Host, port, title, version, **`cors_origins`** |
| `database` | Host, port, name, user, `password_env`, pool sizing |
| `auth` | `jwt_secret_env`, algorithm, `access_token_expire_minutes` |
| `pricing` | Base hourly rate, weekday surcharges, holiday surcharges |
| `planning` | Working-day bounds, lunch window, travel speeds, solver budget, penalties, **seed values** for the manager-owned settings |
| `geocoding` | Nominatim base URL, user agent, timeout, country codes |
| `email` | `enabled`, host, port, TLS, sender, `username_env`, `password_env` |
| `webhook` | `enabled`, URL, `token_env` |
| `s3` | Bucket, region, endpoint, `public_base_url`, key env names, `photo_key_prefix`, `max_upload_bytes` |
| `rabbitmq` | `enabled`, host, port, vhost, user, `password_env`, exchange, publish timeout, `prefetch` |

Each is a Pydantic model with its own validators and its own `MT*` exception
family, so a malformed value fails at start-up naming the field rather than at
first use naming nothing.

## Secrets

**No password is ever written into a YAML file.** A `*_env` key names the
variable, and the value is read at connection time — so rotating a secret needs
a restart, not a rebuild.

| Variable | Named by | Read at |
|---|---|---|
| `RT_ERP_CONFIG` | — | start-up |
| `POSTGRES_PASSWORD` | `database.password_env` | connect |
| `JWT_SECRET_KEY` | `auth.jwt_secret_env` | sign / verify |
| `S3_ACCESS_KEY` · `S3_SECRET_KEY` | `s3.access_key_env` · `secret_key_env` | upload |
| `SMTP_USERNAME` · `SMTP_PASSWORD` | `email.username_env` · `password_env` | send |
| `PLANNING_WEBHOOK_TOKEN` | `webhook.token_env` | call / verify |
| `RABBITMQ_PASSWORD` | `rabbitmq.password_env` | connect |
| `VITE_API_BASE_URL` | — | front-end **build** |

Start from `.env.example`. The development overlay falls back to well-known
defaults; **the production overlay does not** — every variable is `${VAR:?}`
there, so a stack launched without them refuses to start rather than coming up
with `change-me-in-any-real-deployment` as its signing key.

## Three settings that behave unexpectedly

**`VITE_API_BASE_URL` is a build argument, not a runtime variable.** Vite inlines
every `VITE_*` value into the bundle at build time, so setting it on a running
container does nothing. It is passed as a Docker `ARG` in production.

**`cors_origins` is YAML-only.** There is no `*_env` escape hatch, so deploying
to a new front-end origin means editing the configuration file rather than
setting a variable.

**The `planning` block is a seed.** `max_intervention_radius_km` and
`lunch_break_minutes` populate `PlanningSettings` on first read and are never
consulted again. After that a manager owns them through the API, and editing the
file will not move a running deployment. → [06](06-planning-computation.md)

## Two defaults chosen deliberately

**`email.enabled: false`** outside the development overlay, so a developer's
machine never opens an SMTP connection by accident. A disabled service raises
`MTEmailNotConfigured` rather than silently doing nothing.

**`rabbitmq.enabled: false`** in `app.yaml`, so somebody running the API alone is
not blocked by the absence of a broker: a publish that cannot connect is logged
and dropped, and the database still holds every fact the message carried.

## Logging

`backend/conf/logger.yaml` — colourised console plus a rotating
`logs/backend.log`, 10 MB × 7. The worker reads the same file, so its output is
greppable alongside the API's.

Every service and repository takes `logger: Optional[Logger] = None` and defaults
to a logger named after its module, with `%s` lazy formatting. Secrets are never
logged: `DatabaseConfig.dsn_without_password` and
`RabbitMqConfig.url_without_password` exist so a connection failure can name
*which* server without putting the credential in a log file.
