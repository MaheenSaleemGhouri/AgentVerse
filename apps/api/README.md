# apps/api

AgentVerse's orchestration/control-plane API gateway — FastAPI, async Python, Clean Architecture.

## Owned surface (Phase 0)

`GET /health` (liveness) and `GET /ready` (readiness) only. No `/api/v1` business route exists yet — the first real resource (`workspaces`) lands in Phase 1 (`docs/roadmap.md`).

## Layering

```
src/agentverse_api/
├── domain/          # entities, zero framework imports — empty until Phase 1
├── application/      # use cases, depends inward on domain only — empty until Phase 1
├── infrastructure/    # config, logging (this phase); Postgres/Redis/vector DB/LLM clients (later)
└── interface/         # FastAPI routers, schemas, middleware — health/ready only, for now
```

Dependencies point inward (`CLAUDE.md` §5): `interface` depends on `application`, `application` depends on `domain`, `infrastructure` implements ports `domain`/`application` define. No layer imports outward.

## Datastore

None owned yet. Phase 1 introduces `workspaces`/`workspace_members`/`users` in Postgres, owned by this service.

## Dependencies

None yet. Phase 1+ adds Postgres and Redis.

## Local development

```bash
cd apps/api
uv sync
uv run uvicorn agentverse_api.main:app --reload --port 8000
```

## Scripts

- `uv run uvicorn agentverse_api.main:app --reload` — dev server with hot reload.
- `uv run pytest` — unit tests (async, no I/O yet — nothing to fake).
- `uv run ruff check .` — lint.
- `uv run ruff format --check .` — format check.
- `uv run mypy src` — strict type check.
