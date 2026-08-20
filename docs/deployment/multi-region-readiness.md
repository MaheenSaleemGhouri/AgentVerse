# Multi-Region Readiness

See `docs/adr/0019-multi-region-topology.md` for the architecture decision and rationale. This doc is the honest status report: what's deployed today versus the target, stated plainly per CLAUDE.md's rule against claiming capability that isn't real.

## Status: single region, one real building block shipped

**Deployed today:** one Render region (`oregon`, `render.yaml`), matching `docs/deployment/vercel-production.md`'s own status for the rest of the stack (`apps/api`/`apps/worker` are not deployed at all yet in this environment — see that doc). There is no second region, no cross-region routing, no read replica, and no `workspaces.region` column. Every workspace's data lives in the one Postgres instance this deployment has.

**Shipped now:** `Settings.region` (`apps/api`, default `"primary"`) surfaced on `/health` and `/ready`. This is real and tested — the field exists, is wired through, and every response carries it. It is not, by itself, multi-region capability; it is the config surface every later regional-awareness mechanism (health-check routing, region-tagged logs/traces, the eventual `workspaces.region` column) will read from, so it exists once rather than being invented per-consumer when a second region actually ships.

## Target (per ADR-0019, not yet built)

| Piece | Status |
|---|---|
| Global routing to nearest healthy region | Not built |
| Second region's `apps/api`/`apps/worker` deployment | Not built (first region isn't deployed yet either, per `vercel-production.md`) |
| Postgres read replica per region | Not built |
| `workspaces.region` (home-region assignment) | Not built — schema change, ships when a second region is provisioned |
| Region-scoped Redis (queue/cache) | Implicit today — the single Redis instance is trivially "region-local" since there's only one region |
| `AGENTVERSE_API_REGION` config surface | **Shipped** |

## Provisioning a second region (next real step, not yet done)

1. Deploy a full second `apps/api` + `apps/worker` pair in the target region, `AGENTVERSE_API_REGION`/worker-equivalent set to that region's identifier, everything else identical config (twelve-factor).
2. Provision a Postgres read replica in that region, tracking the primary in the first region.
3. Point that region's read-heavy queries (dashboard, run history, marketplace browse) at the local replica; writes continue to the primary region over the network until `workspaces.region`-based routing exists.
4. Add global routing (DNS/anycast or CDN edge routing) once both regions are health-check-verified independently — `/health`/`/ready` already report which region answered, which is exactly what a routing layer's health check needs.
5. Add `workspaces.region`, defaulted to the existing single region for every current workspace (additive migration, CLAUDE.md §8), before offering region choice at workspace creation.

No step here is fabricated infrastructure — this is the ordered list ADR-0019's target topology implies, stated as work not yet started.
