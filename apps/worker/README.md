# apps/worker

AgentVerse's background agent-runtime worker fleet — Python, Clean Architecture.

## Owned surface (Phase 0)

`GET /health` / `GET /ready` only, served over a minimal ASGI app (see `interface/__init__.py` for why). No queue consumer exists yet — Phase 3 (`docs/roadmap.md`) introduces the Redis-backed job queue and the first real job type. Long-running agent execution is always dispatched here, never run inline in an `apps/api` request (`CLAUDE.md` §5, Rule 14) — this service is where that work will land starting Phase 3.

## Layering

Mirrors `apps/api`: `domain/` → `application/` → `infrastructure/` → `interface/`, dependencies pointing inward.

## Datastore

None owned yet. Phase 3 adds Redis (queue) as a dependency; no owned Postgres table until later phases route job records through it if needed.

## Dependencies

None yet. Phase 3 adds Redis.

## Local development

```bash
cd apps/worker
uv sync
uv run uvicorn agentverse_worker.main:app --reload --port 8001
```

## Scripts

- `uv run uvicorn agentverse_worker.main:app --reload` — dev server with hot reload.
- `uv run pytest` — unit tests.
- `uv run ruff check .` — lint.
- `uv run ruff format --check .` — format check.
- `uv run mypy src` — strict type check.
