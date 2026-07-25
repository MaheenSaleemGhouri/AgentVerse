# apps/api

AgentVerse's orchestration/control-plane API gateway — FastAPI, async Python, Clean Architecture.

## Owned surface (Phase 1)

`GET /health`, `GET /ready` (liveness/readiness). `/api/v1/workspaces` (create/get, member invite/role-change/remove), `/api/v1/workspaces/{workspace_id}/api-keys` (issue/list/revoke). `/internal/auth-events` (server-to-server only, shared-secret protected — apps/web's Better Auth hooks report signup/login here so `audit_logs` stays the single home for every auth-relevant event; see `docs/adr/0005-auth-provider-and-schema-ownership.md`).

## Layering

```
src/agentverse_api/
├── domain/, application/, infrastructure/, interface/   # cross-cutting only (config, logging, health) — no business logic
└── auth_service/                                         # bounded context (docs/adr/0004, docs/adr/0005)
    ├── domain/          # Role, entities, exceptions, ports (Protocols) — zero framework imports
    ├── application/      # use cases: WorkspaceService, ApiKeyService, AuditService, AuthEventService
    ├── infrastructure/    # SQLAlchemy models (Alembic-owned schema), repositories, JWT/JWKS verifier
    └── interface/         # get_current_identity, get_current_workspace, require_role dependencies; routes; schemas
```

Dependencies point inward (`CLAUDE.md` §5). `auth_service` is a self-contained vertical slice — ready to become `apps/api/src/agentverse_api/orchestration_service` etc. in later phases, or to be extracted into its own deployable if `microservices-architect`'s "concrete pain" threshold is ever reached (`docs/adr/0004`).

## Datastore

Owns (via Alembic, `src/agentverse_api/infrastructure/migrations/`): `users`, `sessions`, `accounts`, `verifications` (Better Auth's schema, ADR-0005 — Alembic authors it, Better Auth only reads/writes through it), `workspaces`, `workspace_members`, `api_keys`, `audit_logs` (this platform's own domain).

## Dependencies

Postgres (`DATABASE_URL`). Better Auth's JWKS endpoint (`AUTH_INTERNAL_URL`, apps/web) for JWT verification — no shared secret with apps/web for that path (`AUTH_PUBLIC_URL` is the separate, browser-facing origin used only for issuer/audience validation — see `.env.example` for why these two must differ under Docker Compose). A separate shared secret (`INTERNAL_API_SECRET`) protects the one server-to-server endpoint, `/internal/auth-events`.

## Local development

```bash
cd apps/api
uv sync
cp .env.example .env   # then fill in DATABASE_URL / AUTH_INTERNAL_URL / AUTH_PUBLIC_URL / INTERNAL_API_SECRET
uv run alembic upgrade head
uv run uvicorn agentverse_api.main:app --reload --port 8000
```

## Migrations

```bash
uv run alembic revision --autogenerate -m "description"   # generate, then review before committing
uv run alembic upgrade head                                 # apply
uv run alembic downgrade -1                                  # roll back one — test this, not just write it
```

Alembic is the only schema-authoring tool against this database, including for Better Auth's tables (`CLAUDE.md` §8 — see `docs/adr/0005`). Autogenerate does not reliably emit `DROP TYPE` for Postgres ENUM columns on downgrade — verified and hand-fixed once for `workspace_role`; check this again for any future ENUM column.

## Regenerating the OpenAPI contract

`openapi.json` in this directory is a checked-in static export, consumed by `packages/contracts`' type generation:

```bash
uv run python -c "
import json
from agentverse_api.main import create_app
print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
" > openapi.json
cd ../../packages/contracts && pnpm run generate
```

Run both steps (and commit the diff in both repos) whenever a route or Pydantic schema changes.

## Scripts

- `uv run uvicorn agentverse_api.main:app --reload` — dev server with hot reload.
- `uv run pytest` — unit tests (fakes, no I/O) by default; `uv run pytest -m integration` runs the real-Postgres suite (needs `DATABASE_URL`).
- `uv run ruff check .` — lint.
- `uv run ruff format --check .` — format check.
- `uv run mypy src` — strict type check.
