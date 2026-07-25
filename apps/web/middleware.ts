import { getSessionCookie } from "better-auth/cookies";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Thin auth/redirect only — no business logic or data fetching
 * (CLAUDE.md §6). This is an optimistic cookie-presence check, not a
 * verified session check (Better Auth's own documented middleware
 * pattern: Edge-compatible, no DB call). Real verification happens in
 * the protected route group's layout via `auth.api.getSession`.
 */
export function middleware(request: NextRequest): NextResponse {
  const sessionCookie = getSessionCookie(request);

  if (!sessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
