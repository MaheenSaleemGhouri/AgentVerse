import * as argon2 from "argon2";

/**
 * Argon2id, not Better Auth's scrypt default (ADR-0005 — CLAUDE.md §10
 * requires bcrypt/argon2). Wired into Better Auth's own pluggable
 * `emailAndPassword.password.{hash,verify}` interface.
 */

export async function hashPassword(password: string): Promise<string> {
  return argon2.hash(password, { type: argon2.argon2id });
}

export async function verifyPassword(data: { password: string; hash: string }): Promise<boolean> {
  return argon2.verify(data.hash, data.password);
}
