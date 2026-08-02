import "server-only";

/**
 * Better Auth session cookie, written from outside a Better Auth endpoint.
 *
 * The SAML assertion consumer (Increment 8b) establishes a session from a
 * plain Next route handler, so it has no `GenericEndpointContext` and
 * cannot call Better Auth's own `setSessionCookie`. What it must not do is
 * write the raw session token: Better Auth stores that cookie **signed**
 * (`better-call`'s `serializeSignedCookie`), and an unsigned value is
 * rejected on the very next request — the session would look created and
 * then silently not exist.
 *
 * This reproduces exactly that wire format and nothing more:
 *   value = encodeURIComponent(`${token}.${base64(HMAC-SHA256(token))}`)
 * The `encodeURIComponent` step is applied by Next's own cookie
 * serializer, so the value handed to `cookies.set` stays undecorated.
 */

async function signCookieValue(value: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(value)
  );
  return btoa(String.fromCharCode(...new Uint8Array(signature)));
}

/** Structurally `better-call`'s `CookieOptions` for the fields that matter
 *  here — every one is optional there, so each falls back to the same
 *  default `createCookieGetter` applies. */
export interface SessionCookieAttributes {
  httpOnly?: boolean | undefined;
  secure?: boolean | undefined;
  path?: string | undefined;
  sameSite?: "Strict" | "Lax" | "None" | "strict" | "lax" | "none" | undefined;
  domain?: string | undefined;
}

export interface PreparedSessionCookie {
  value: string;
  options: {
    httpOnly: boolean;
    secure: boolean;
    path: string;
    sameSite: "strict" | "lax" | "none";
    expires: Date;
    domain?: string;
  };
}

export async function prepareSessionCookie({
  token,
  secret,
  attributes,
  expiresAt,
}: {
  token: string;
  secret: string;
  attributes: SessionCookieAttributes;
  expiresAt: Date;
}): Promise<PreparedSessionCookie> {
  const signature = await signCookieValue(token, secret);
  return {
    value: `${token}.${signature}`,
    options: {
      httpOnly: attributes.httpOnly ?? true,
      secure: attributes.secure ?? false,
      path: attributes.path ?? "/",
      sameSite: (attributes.sameSite ?? "lax").toLowerCase() as "strict" | "lax" | "none",
      expires: expiresAt,
      ...(attributes.domain ? { domain: attributes.domain } : {}),
    },
  };
}
