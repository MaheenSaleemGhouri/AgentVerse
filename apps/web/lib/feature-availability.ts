/**
 * The single registry of which product surfaces have a backend yet.
 *
 * AgentVerse ships its frontend ahead of several roadmap phases. Rather
 * than let each unbacked screen invent its own placeholder — or worse,
 * render fabricated numbers that look real — every such screen reads
 * from here and renders `<IntegrationPending>` with the exact endpoint
 * it is waiting on and the phase that delivers it.
 *
 * A dashboard showing invented revenue is worse than one that says what
 * it is waiting for: the first silently misinforms, the second is
 * honest and points at the work.
 *
 * When a phase lands, delete the entry — the screen's real data path is
 * then the only path, and any leftover pending panel fails the build
 * because its key no longer exists.
 */

export interface PendingIntegration {
  /** Roadmap phase that delivers the backend (docs/roadmap.md). */
  readonly phase: number;
  readonly phaseName: string;
  /** The endpoints this screen will consume once they exist. */
  readonly endpoints: readonly string[];
  /** What the user will be able to do here, stated concretely. */
  readonly capability: string;
}

export const PENDING_INTEGRATIONS = {
  /**
   * The one gap that is *not* a future phase: Phase 4 shipped run
   * submission (`POST .../runs`) and live streaming
   * (`GET .../runs/{id}/stream`) but no way to read runs back. So a run
   * is fully visible while it happens and unreachable after a reload.
   *
   * This blocks dashboard activity, agent run history, and analytics.
   * It needs a read-only list/detail endpoint over `agent_runs` —
   * small, but backend work, and this sprint is frontend-scoped.
   */
  runHistory: {
    phase: 4,
    phaseName: "Single-Agent Builder, Runtime & Live Execution (already shipped — read path missing)",
    endpoints: [
      "GET /api/v1/workspaces/{workspace_id}/agents/{agent_id}/runs",
      "GET /api/v1/workspaces/{workspace_id}/agents/{agent_id}/runs/{run_id}",
    ],
    capability:
      "Read past runs back after the live stream ends — run history, dashboard activity, and the data every analytics chart aggregates.",
  },
  // `mcp`, `integrations`, and `workflows` were removed when their
  // phases shipped. Deleting the entry rather than leaving it is the
  // point of this registry: any leftover `<IntegrationPending
  // feature="workflows" />` now fails the TypeScript build instead of
  // lingering as stale UI over a working backend (Phase 10,
  // docs/adr/0016).
  analytics: {
    phase: 11,
    phaseName: "Growth Loops & Multi-Provider Breadth",
    endpoints: [
      "GET /api/v1/workspaces/{workspace_id}/analytics/runs",
      "GET /api/v1/workspaces/{workspace_id}/analytics/usage",
    ],
    capability:
      "Aggregated run volume, success rate, latency percentiles, and per-model cost attribution over time.",
  },
  /**
   * `notification_service` sends real notifications (see
   * `notification_service/domain/notification.py`'s `NotificationKind`)
   * but has no per-channel opt-in/out concept — `domain/ports.py` has no
   * preference or mute port. Unlike the other entries here, this was
   * never scoped into a numbered roadmap phase, so `phase` marks it as
   * backlog rather than citing a phase that doesn't cover it.
   */
  notificationPreferences: {
    phase: 13,
    phaseName: "Notification preferences (not yet scheduled on the roadmap)",
    endpoints: [
      "GET /api/v1/workspaces/{workspace_id}/notification-preferences",
      "PATCH /api/v1/workspaces/{workspace_id}/notification-preferences",
    ],
    capability:
      "Choose which notification categories (billing, agent runs, team, security) arrive by email vs. in-app only, per user.",
  },
} as const satisfies Record<string, PendingIntegration>;

export type PendingIntegrationKey = keyof typeof PENDING_INTEGRATIONS;
