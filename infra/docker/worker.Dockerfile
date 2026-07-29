# syntax=docker/dockerfile:1
# apps/worker — background agent-runtime fleet. Same pattern as
# infra/docker/api.Dockerfile; see that file for the dev/non-root and
# repo-mirroring rationale (the shared package is resolved by relative
# path, so the layout inside the image has to mirror the repo).
# Build with: docker build -f infra/docker/worker.Dockerfile --target dev .

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

FROM base AS dev
WORKDIR /src/apps/worker
COPY packages/python-shared /src/packages/python-shared
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen
COPY apps/worker/ .
EXPOSE 8001
CMD ["uv", "run", "uvicorn", "agentverse_worker.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

FROM base AS builder
WORKDIR /src/apps/worker
COPY packages/python-shared /src/packages/python-shared
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
COPY apps/worker/ .
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN addgroup --system agentverse && adduser --system --ingroup agentverse agentverse
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=agentverse:agentverse /src/apps/worker /app
USER agentverse
EXPOSE 8001
CMD ["uvicorn", "agentverse_worker.main:app", "--host", "0.0.0.0", "--port", "8001"]
