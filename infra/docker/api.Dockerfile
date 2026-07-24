# syntax=docker/dockerfile:1
# apps/api — FastAPI, built from the repo root as build context so the
# uv-managed venv only ever contains this service's own dependencies.
# Build with: docker build -f infra/docker/api.Dockerfile --target dev .

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

# ---- dev: hot-reload dev server, used by docker-compose. Runs as root
# for bind-mount write compatibility across host platforms — the
# production `runtime` stage below is the one CLAUDE.md §12's
# non-root requirement targets, since it's the one that ships. ----
FROM base AS dev
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen
COPY apps/api/ .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "agentverse_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- builder: production dependency set, no dev tools ----
FROM base AS builder
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY apps/api/ .
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime: minimal final image, no build toolchain, non-root ----
FROM python:3.12-slim AS runtime
RUN addgroup --system agentverse && adduser --system --ingroup agentverse agentverse
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=agentverse:agentverse /app /app
USER agentverse
EXPOSE 8000
CMD ["uvicorn", "agentverse_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
