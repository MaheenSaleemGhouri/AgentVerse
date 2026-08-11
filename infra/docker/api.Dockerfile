# syntax=docker/dockerfile:1
# apps/api — FastAPI, built from the repo root as build context so the
# uv-managed venv only ever contains this service's own dependencies.
# Build with: docker build -f infra/docker/api.Dockerfile --target dev .
#
# The layout inside the image mirrors the repo (`/src/apps/api`,
# `/src/packages/python-shared`) rather than flattening the service to
# `/app`. That is not cosmetic: `apps/api/pyproject.toml` declares
# `agentverse-shared = { path = "../../packages/python-shared" }`, and a
# relative path only resolves if the two keep their relative positions.
# Flattening produced `cannot normalize a relative path beyond the base
# directory` at `uv sync` — the image simply did not build.

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
WORKDIR /src/apps/api
# The shared package is copied before `uv sync` because the sync
# resolves it from disk. Copied whole rather than manifest-first: it is
# small, and splitting it would add a layer whose cache invalidates on
# the same edits anyway.
COPY packages/python-shared /src/packages/python-shared
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen
COPY apps/api/ .
EXPOSE 8000
# Migrations run automatically here because this is a single-instance
# local dev stack. Production/staging never does this on container
# start — with multiple replicas, simultaneous `alembic upgrade` runs
# race each other; migrations there are a separate one-shot deploy
# step before new replicas roll out (CLAUDE.md §12).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn agentverse_api.main:app --host 0.0.0.0 --port 8000 --reload"]

# ---- builder: production dependency set, no dev tools ----
FROM base AS builder
WORKDIR /src/apps/api
COPY packages/python-shared /src/packages/python-shared
COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY apps/api/ .
# `--no-editable` builds the shared package into the venv as a real
# wheel, so the runtime stage below does not need the source tree.
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime: minimal final image, no build toolchain, non-root ----
FROM python:3.12-slim AS runtime
RUN addgroup --system agentverse && adduser --system --ingroup agentverse agentverse
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Flattened back to /app here deliberately: the shared package is a
# built wheel inside .venv at this point, so nothing resolves a relative
# path any more and the final image carries no `packages/` tree.
COPY --from=builder --chown=agentverse:agentverse /src/apps/api /app
USER agentverse
EXPOSE 8000
# `python -m uvicorn`, not the `uvicorn` console script: `uv sync` bakes
# the venv's build-time absolute path (/src/apps/api/.venv/...) into
# every console-script shebang, which no longer exists once this stage
# copies the venv to /app — `exec: no such file or directory` at
# container start. Invoking the module via the interpreter on PATH
# sidesteps the shebang entirely.
CMD ["python", "-m", "uvicorn", "agentverse_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
