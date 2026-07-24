# apps/worker — background agent-runtime fleet. Same pattern as
# infra/docker/api.Dockerfile; see that file for the dev/non-root rationale.
# Build with: docker build -f infra/docker/worker.Dockerfile --target dev .
syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

FROM base AS dev
WORKDIR /app
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN uv sync --frozen
COPY apps/worker/ .
EXPOSE 8001
CMD ["uv", "run", "uvicorn", "agentverse_worker.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

FROM base AS builder
WORKDIR /app
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
COPY apps/worker/ .
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN addgroup --system agentverse && adduser --system --ingroup agentverse agentverse
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=agentverse:agentverse /app /app
USER agentverse
EXPOSE 8001
CMD ["uvicorn", "agentverse_worker.main:app", "--host", "0.0.0.0", "--port", "8001"]
