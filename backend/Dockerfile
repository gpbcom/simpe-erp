FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY models/pyproject.toml ./models/
COPY storage/pyproject.toml ./storage/
COPY service/pyproject.toml ./service/
COPY api/pyproject.toml ./api/
COPY worker/pyproject.toml ./worker/
COPY seed/pyproject.toml ./seed/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev

COPY models ./models
COPY storage ./storage
COPY service ./service
COPY api ./api
COPY worker ./worker
COPY seed ./seed
# A plain module rather than a distribution of its own. The workspace root
# ships it, so it has to be present before the root project is built below.
COPY integrations ./integrations

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.14-slim-bookworm AS runtime


RUN groupadd --system --gid 1001 rterp \
    && useradd --system --uid 1001 --gid rterp --create-home rterp

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SIMPLE_ERP_CONFIG=conf/app.docker.yaml

WORKDIR /app

COPY --from=builder --chown=rterp:rterp /app/.venv /app/.venv
COPY --from=builder --chown=rterp:rterp /app/models /app/models
COPY --from=builder --chown=rterp:rterp /app/storage /app/storage
COPY --from=builder --chown=rterp:rterp /app/service /app/service
COPY --from=builder --chown=rterp:rterp /app/api /app/api
COPY --from=builder --chown=rterp:rterp /app/worker /app/worker
COPY --from=builder --chown=rterp:rterp /app/seed /app/seed
COPY --from=builder --chown=rterp:rterp /app/integrations /app/integrations
COPY --chown=rterp:rterp conf ./conf

RUN mkdir -p /app/logs && chown rterp:rterp /app/logs

USER rterp

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready').read()"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
