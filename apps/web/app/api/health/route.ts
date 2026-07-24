import { NextResponse } from "next/server";

/**
 * Liveness probe: is the Next.js process up and serving requests at all.
 * No dependency checks here — that's /api/ready's job (CLAUDE.md §12).
 */
export function GET(): NextResponse {
  return NextResponse.json({ status: "ok" });
}
