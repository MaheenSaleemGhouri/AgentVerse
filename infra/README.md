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

## Verified

`docker compose up --build` has been run end-to-end (Docker Desktop 4.61.0, Engine 29.2.1). All 5 containers (`postgres`, `redis`, `api`, `worker`, `web`) reach `healthy`, in the correct dependency order. Confirmed live: `pgvector` extension creates successfully on the `postgres` container (`CREATE EXTENSION vector` → v0.8.2); `redis-cli PING` → `PONG`; all `/health`/`/ready` routes return `200 {"status":"ok"}` through the mapped host ports; `docker compose down` cleanly stops and removes all containers/network.

**Dev-mode hot reload note:** the `web` service's dev target needs `WATCHPACK_POLLING=true` (already set in `docker/web.Dockerfile`) — webpack's native filesystem watcher does not see host-side edits through a Docker Desktop bind mount on Windows; confirmed broken without the polling env var, confirmed working with it (~1s detection). `api`/`worker`'s `uvicorn --reload` (via `watchfiles`) did not need this — it detected bind-mounted changes correctly out of the box.

**node_modules named-volume staleness (real, reproduced):** the `web_*_node_modules` volumes exist so container-native installs never get shadowed by a host bind mount (Phase 0). The tradeoff: **Docker never re-syncs a named volume's content from a rebuilt image** — once a volume exists, it keeps whatever was installed the first time, even after `docker compose build` picks up new dependencies. Adding `better-auth`/`pg`/`argon2` to `apps/web/package.json` in Phase 1 reproduced this exactly: `docker compose up --build` succeeded, the image had the new packages, but the *running container* still showed `better-auth` missing, because the old volume (created before those deps existed) was mounted over the new image's `node_modules`. Rebuilding the image again, even with `--no-cache`, does not fix this — the volume is the problem, not the image.

**Fix:** whenever a `package.json` dependency changes, run `docker compose down -v` (removes the named volumes too — and `postgres_data`, so migrations re-run on next start) before `docker compose up --build`, not just a rebuild. A targeted `docker volume rm infra_web_app_node_modules infra_web_root_node_modules infra_contracts_node_modules` works too if you want to keep `postgres_data`.

## Dependencies

None — this is infrastructure, not a service with its own dependents.
