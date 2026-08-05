# rt-erp backend image.
#
# Two stages: the first resolves and installs the dependency tree, the second
# carries only the runtime. Keeping the build tooling out of the shipped image
# is worth the extra stage — uv, a compiler toolchain and a full package cache
# are a large attack surface for something that never runs in production.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# The manifests are copied on their own first. Docker caches this layer on
# their content, so editing application code does not re-resolve the whole
# dependency tree — which, with ortools in it, is not a fast operation.
COPY pyproject.toml uv.lock ./
COPY models/pyproject.toml ./models/
COPY storage/pyproject.toml ./storage/
COPY service/pyproject.toml ./service/
COPY api/pyproject.toml ./api/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev

COPY models ./models
COPY storage ./storage
COPY service ./service
COPY api ./api

# Now the workspace members themselves, once their dependencies are in place.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.14-slim-bookworm AS runtime

# Runs as a non-root user. A container that is compromised through the web
# surface should not also own the filesystem it is running on.
RUN groupadd --system --gid 1001 rterp \
    && useradd --system --uid 1001 --gid rterp --create-home rterp

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RT_ERP_CONFIG=conf/app.docker.yaml

WORKDIR /app

COPY --from=builder --chown=rterp:rterp /app/.venv /app/.venv
COPY --from=builder --chown=rterp:rterp /app/models /app/models
COPY --from=builder --chown=rterp:rterp /app/storage /app/storage
COPY --from=builder --chown=rterp:rterp /app/service /app/service
COPY --from=builder --chown=rterp:rterp /app/api /app/api
COPY --chown=rterp:rterp conf ./conf

# The log configuration writes a rotating file, so the directory has to exist
# and be writable by the runtime user before the first record is emitted.
RUN mkdir -p /app/logs && chown rterp:rterp /app/logs

USER rterp

EXPOSE 8000

# Checks readiness, not liveness: /health answers as soon as the process is up,
# whereas /ready also proves the database is reachable, which is what makes the
# container worth routing traffic to.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready').read()"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
