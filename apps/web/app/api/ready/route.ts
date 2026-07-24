import { NextResponse } from "next/server";

/**
 * Readiness probe: are this service's hard dependencies reachable.
 * apps/web has no hard runtime dependency yet in Phase 0 — it doesn't
 * call apps/api for anything — so readiness currently reduces to
 * liveness. This route stays separate from /api/health so that adding
 * a real dependency check later (e.g. apps/api reachability) doesn't
 * require introducing a new route and updating docker-compose/orchestrator
 * health-check wiring — only this handler's body changes.
 */
export function GET(): NextResponse {
  return NextResponse.json({ status: "ok" });
}
