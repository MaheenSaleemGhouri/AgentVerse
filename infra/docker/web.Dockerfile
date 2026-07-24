# syntax=docker/dockerfile:1
# apps/web — Next.js 15, built from the pnpm workspace root as build context.
# Build with: docker build -f infra/docker/web.Dockerfile --target dev .

FROM node:20.20.2-alpine AS base
# The Corepack build bundled with this Node image ships a stale signing-key
# set and fails to verify current npm registry signatures ("Cannot find
# matching keyid") — update Corepack itself first rather than disabling
# signature verification (COREPACK_INTEGRITY_KEYS=0), which would remove
# the check instead of fixing the stale-key cause of it.
RUN npm install -g corepack@latest && corepack enable && corepack prepare pnpm@9.15.9 --activate

# ---- deps: install once, shared by dev and builder ----
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc tsconfig.base.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN pnpm install --frozen-lockfile

# ---- dev: hot-reload dev server, used by docker-compose ----
FROM deps AS dev
WORKDIR /repo
COPY . .
WORKDIR /repo/apps/web
# Webpack's native fs-watch doesn't see host-side edits through Docker
# Desktop's Windows-host bind mount (confirmed: editing a file host-side
# never triggered a recompile without this) — fall back to polling.
ENV WATCHPACK_POLLING=true
EXPOSE 3000
CMD ["pnpm", "dev"]

# ---- builder: production build, standalone output ----
FROM deps AS builder
WORKDIR /repo
COPY . .
RUN pnpm --filter @agentverse/contracts run build
RUN pnpm --filter @agentverse/web run build

# ---- runtime: minimal final image, no build toolchain, non-root ----
FROM node:20.20.2-alpine AS runtime
RUN addgroup -S agentverse && adduser -S agentverse -G agentverse
WORKDIR /repo
ENV NODE_ENV=production
COPY --from=builder --chown=agentverse:agentverse /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=agentverse:agentverse /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=agentverse:agentverse /repo/apps/web/public ./apps/web/public
USER agentverse
EXPOSE 3000
ENV PORT=3000
CMD ["node", "apps/web/server.js"]
