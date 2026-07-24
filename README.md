# AgentVerse

Enterprise platform for building, deploying, and orchestrating AI agents and multi-agent systems.

This repository is governed by [`CLAUDE.md`](./CLAUDE.md) (the engineering constitution), [`docs/project-memory.md`](./docs/project-memory.md) (product context), [`docs/decision-log.md`](./docs/decision-log.md) (technical precedent), [`docs/ai-playbook.md`](./docs/ai-playbook.md) (how work gets planned and reviewed), and [`docs/roadmap.md`](./docs/roadmap.md) (the phased build sequence). Read them in that order before making a non-trivial change — `docs/ai-playbook.md` §9 fixes this as the required context-loading order.

**Current state: Phase 0 complete.** Repo scaffolding, local dev stack, and CI exist; there is no product feature yet. See `docs/roadmap.md` Phase 0 for exactly what that means and Phase 1 for what's next.

## Repository layout

```
apps/
├── web/                # Next.js 15 (App Router), React 19, TypeScript strict, Tailwind CSS v4
├── api/                 # FastAPI orchestration/control-plane gateway (Clean Architecture)
└── worker/               # Background agent-runtime worker fleet (Clean Architecture)
packages/
└── contracts/            # Shared OpenAPI-generated TypeScript contracts
infra/
├── docker-compose.yml     # Local dev stack: Postgres+pgvector, Redis, all three services
└── docker/                # Per-service multi-stage Dockerfiles
docs/
├── adr/                  # Architecture decision records
├── architecture/          # Service map and cross-service flow diagrams
└── systems/                # Logging schema, health-check contract, OTel conventions
.claude/skills/             # The 80-skill AI engineering library this org operates as
```

Each service owns its own `README.md`, `.env.example`, and (for the Python services) `pyproject.toml`/`uv.lock` — see `apps/*/README.md` for what each one actually does today versus what lands in a later phase.

## Bootstrap (local development)

**Prerequisites:** Node.js ≥20.9 (`.nvmrc` pins `20.18.0`), `pnpm` (via Corepack: `corepack enable`), Python 3.12, [`uv`](https://docs.astral.sh/uv/), and Docker with Compose v2.

> **WSL note:** clone into the Linux filesystem (e.g. `~/code/AgentVerse`), not `/mnt/c/...`. Installs and `next build` are dramatically slower across the 9P filesystem bridge — this was the dominant cost observed while building Phase 0 (a `next build` took ~60s from `/mnt/c` for a near-empty app).

```bash
# 1. JS/TS side (apps/web, packages/contracts)
pnpm install
pnpm build        # builds packages/contracts and apps/web
pnpm lint
pnpm typecheck

# 2. Python side (apps/api, apps/worker) — each is its own uv project
cd apps/api && uv sync && uv run pytest -q && cd ../..
cd apps/worker && uv sync && uv run pytest -q && cd ../..

# 3. Full local stack via Docker Compose (Postgres+pgvector, Redis, all 3 services)
cd infra
cp .env.example .env
docker compose up --build
```

Once healthy: `apps/web` → http://localhost:3000, `apps/api` → http://localhost:8000, `apps/worker` → http://localhost:8001. Every service exposes `/health` (liveness) and `/ready` (readiness) — see `docs/systems/health-checks.md`.

## Running each service directly (without Docker)

```bash
pnpm --filter @agentverse/web dev                                            # :3000, hot reload
cd apps/api && uv run uvicorn agentverse_api.main:app --reload --port 8000    # :8000, hot reload
cd apps/worker && uv run uvicorn agentverse_worker.main:app --reload --port 8001  # :8001, hot reload
```

## CI

Every PR runs lint → type-check → build/test → dependency audit for both the Node and Python tracks (`.github/workflows/ci.yml`), fail-fast, cheapest-first (`CLAUDE.md` §11). `ci-gate` is the single required status check.

## Contributing

PRs use `.github/pull_request_template.md`. `.github/CODEOWNERS` maps paths to owning disciplines per `CLAUDE.md` §18.1. Branch/commit conventions are in `CLAUDE.md` §14.
