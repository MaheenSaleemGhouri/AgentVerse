import { env } from "@/lib/env";

// Must stay in step with `AuthEventType` in
// apps/api/.../application/auth_event_service.py — apps/api validates
// this value against its own Literal, so a value only added here is
// rejected at the boundary rather than silently accepted.
type AuthEventType =
  | "auth.signup"
  | "auth.login"
  | "auth.session_revoked"
  | "auth.account_locked";

/**
 * Reports a signup/login event to apps/api so `audit_logs` stays the
 * single home for every auth-relevant event (ADR-0005), rather than
 * splitting auth history across two services' logs.
 *
 * Best-effort: a failure here must never block the auth flow itself —
 * logged and swallowed, not re-thrown into Better Auth's hook.
 */
export async function reportAuthEvent(eventType: AuthEventType, userId: string): Promise<void> {
  try {
    const response = await fetch(`${env.apiInternalUrl}/internal/auth-events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": env.internalApiSecret,
      },
      body: JSON.stringify({ event_type: eventType, user_id: userId }),
    });
    if (!response.ok) {
      console.error(
        `reportAuthEvent: apps/api returned ${response.status} for ${eventType}/${userId}`
      );
    }
  } catch (error) {
    console.error("reportAuthEvent: failed to reach apps/api", error);
  }
}
