# infra

Local development stack and container definitions for AgentVerse (Phase 0).

## Owned surface

- `docker-compose.yml` — Postgres (with pgvector extension pre-installed, per `docs/adr/0003-vector-database-choice.md`), Redis, and dev-mode containers for `apps/web`, `apps/api`, `apps/worker`.
- `docker/*.Dockerfile` — one multi-stage Dockerfile per service (`dev` / `builder` / `runtime` targets). Dockerfiles live here rather than beside each service, per `docs/roadmap.md` Phase 0's explicit technical-tasks direction.

## Bootstrap

```bash
cd infra
cp .env.example .env
docker compose up --build
```

Run from `infra/` specifically — Docker Compose auto-loads `.env` from its own working directory, which is what resolves `${POSTGRES_USER}` etc. in `docker-compose.yml`. Build context for every service is the repo root (`context: ..`), so each Dockerfile can `COPY` files from anywhere in the monorepo (e.g. `web.Dockerfile` needs `packages/contracts` alongside `apps/web`).

Once healthy:
- `apps/web` → http://localhost:3000 (`/api/health`, `/api/ready`)
- `apps/api` → http://localhost:8000 (`/health`, `/ready`)
- `apps/worker` → http://localhost:8001 (`/health`, `/ready`)
- Postgres → `localhost:5432` (pgvector-enabled)
- Redis → `localhost:6379`

`api` and `worker` both wait on `postgres`/`redis` reporting `service_healthy` before starting; `web` waits on `api`. This is the health-check-gated startup order this phase's acceptance criteria require.

## Known limitation

This sandbox's Docker Engine is unreachable (Docker Desktop WSL integration not enabled in the CI/build environment used to author this stack), so `docker compose up` itself could not be executed end-to-end here. Each Dockerfile and `docker-compose.yml` was written against well-established, documented patterns (Astral's official `uv` Docker image layering, Next.js's official pnpm-monorepo standalone-output recipe) and validated for YAML/structural correctness, but a clean-machine `docker compose up --build` run is the outstanding verification step — do this first when Docker is available, before starting Phase 1.

## Dependencies

None — this is infrastructure, not a service with its own dependents.
