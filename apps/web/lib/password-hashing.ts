import * as argon2 from "argon2";

import { accountLockedError, isLocked, recordFailure, recordSuccess } from "@/lib/account-lock";
import { reportAuthEvent } from "@/lib/report-auth-event";

/**
 * Argon2id, not Better Auth's scrypt default (ADR-0005 — CLAUDE.md §10
 * requires bcrypt/argon2). Wired into Better Auth's own pluggable
 * `emailAndPassword.password.{hash,verify}` interface.
 *
 * `verify` additionally enforces account locking (Increment 7.5) from
 * this same extension point rather than adding a second interception
 * layer. Order matters: the lock is checked *before* the Argon2id
 * comparison, so a locked account short-circuits without spending CPU on
 * a hash whose result would be discarded anyway.
 */

export async function hashPassword(password: string): Promise<string> {
  return argon2.hash(password, { type: argon2.argon2id });
}

export async function verifyPassword(data: { password: string; hash: string }): Promise<boolean> {
  if (await isLocked(data.hash)) {
    throw accountLockedError();
  }

  const valid = await argon2.verify(data.hash, data.password);

  if (valid) {
    await recordSuccess(data.hash);
    return true;
  }

  const failure = await recordFailure(data.hash);
  if (failure) {
    await reportAuthEvent("auth.login_failed", failure.userId);
    if (failure.locked) {
      await reportAuthEvent("auth.account_locked", failure.userId);
    }
  }
  return false;
}
