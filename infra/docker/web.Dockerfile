# apps/web — Next.js 15, built from the pnpm workspace root as build context.
# Build with: docker build -f infra/docker/web.Dockerfile --target dev .
syntax=docker/dockerfile:1

FROM node:20.18.0-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

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
EXPOSE 3000
CMD ["pnpm", "dev"]

# ---- builder: production build, standalone output ----
FROM deps AS builder
WORKDIR /repo
COPY . .
RUN pnpm --filter @agentverse/contracts run build
RUN pnpm --filter @agentverse/web run build

# ---- runtime: minimal final image, no build toolchain, non-root ----
FROM node:20.18.0-alpine AS runtime
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
