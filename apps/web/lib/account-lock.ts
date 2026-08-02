import "server-only";

import { APIError } from "better-auth/api";
import { Pool } from "pg";

import { env } from "@/lib/env";

/**
 * Account locking after repeated failed sign-ins (Increment 7.5).
 *
 * Enforced from inside the already-customized
 * `emailAndPassword.password.verify` override — the same Better Auth
 * extension point ADR-0005 used for Argon2id — rather than a new
 * interception layer. Better Auth passes only `{password, hash}` to
 * `verify`, so the *caller's identity* is resolved here by the account's
 * password hash, which is unique per account in practice (Argon2id
 * salts every hash independently, so two accounts never share one).
 *
 * Deliberately fail-open on a database error: a Postgres blip must not
 * make every sign-in impossible. The lock is a brute-force speed bump,
 * not the primary authentication control — the password check itself
 * still has to pass regardless of what this returns.
 */

/** Consecutive failures before the account locks. */
export const MAX_FAILED_ATTEMPTS = 5;
/** How long a locked account stays locked. */
export const LOCK_DURATION_MS = 15 * 60 * 1000;

let pool: Pool | undefined;

function getPool(): Pool {
  pool ??= new Pool({ connectionString: env.databaseUrl });
  return pool;
}

/**
 * Better Auth's own error type, so a locked account surfaces as a clean
 * `403 ACCOUNT_LOCKED` the client can render — a plain `Error` thrown
 * from inside `password.verify` escapes as an opaque 500 with an empty
 * body (observed live before this was fixed), which is exactly the
 * "something went wrong" failure mode error states are meant to avoid.
 *
 * The message deliberately does not confirm whether the submitted
 * password was correct.
 */
export function accountLockedError(): APIError {
  return new APIError("FORBIDDEN", {
    code: "ACCOUNT_LOCKED",
    message: "Too many failed sign-in attempts. Try again in 15 minutes.",
  });
}

/** Whether this account is currently locked out. */
export async function isLocked(passwordHash: string): Promise<boolean> {
  try {
    const { rows } = await getPool().query<{ locked_until: Date | null }>(
      `SELECT u.locked_until
         FROM users u
         JOIN accounts a ON a.user_id = u.id
        WHERE a.password = $1 AND a.provider_id = 'credential'
        LIMIT 1`,
      [passwordHash]
    );
    const lockedUntil = rows[0]?.locked_until;
    return lockedUntil != null && lockedUntil.getTime() > Date.now();
  } catch (error) {
    console.error("account-lock: lock check failed, allowing the attempt", error);
    return false;
  }
}

/** Clears the failure counter after a successful sign-in. */
export async function recordSuccess(passwordHash: string): Promise<void> {
  try {
    await getPool().query(
      `UPDATE users u
          SET failed_login_count = 0, locked_until = NULL
         FROM accounts a
        WHERE a.user_id = u.id
          AND a.password = $1
          AND a.provider_id = 'credential'
          AND (u.failed_login_count <> 0 OR u.locked_until IS NOT NULL)`,
      [passwordHash]
    );
  } catch (error) {
    console.error("account-lock: could not reset the failure counter", error);
  }
}

/**
 * Increments the failure counter and locks the account once it reaches
 * `MAX_FAILED_ATTEMPTS`. Returns the user id when this attempt caused
 * the lock, so the caller can audit it — `null` otherwise.
 */
export async function recordFailure(passwordHash: string): Promise<string | null> {
  try {
    const { rows } = await getPool().query<{ id: string; failed_login_count: number }>(
      `UPDATE users u
          SET failed_login_count = u.failed_login_count + 1,
              locked_until = CASE
                WHEN u.failed_login_count + 1 >= $2 THEN now() + ($3 || ' milliseconds')::interval
                ELSE u.locked_until
              END
         FROM accounts a
        WHERE a.user_id = u.id
          AND a.password = $1
          AND a.provider_id = 'credential'
        RETURNING u.id, u.failed_login_count`,
      [passwordHash, MAX_FAILED_ATTEMPTS, String(LOCK_DURATION_MS)]
    );
    const row = rows[0];
    if (row && row.failed_login_count >= MAX_FAILED_ATTEMPTS) {
      return row.id;
    }
    return null;
  } catch (error) {
    console.error("account-lock: could not record the failed attempt", error);
    return null;
  }
}
