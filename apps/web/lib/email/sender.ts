import "server-only";

import { Resend } from "resend";

import { env } from "@/lib/env";

/**
 * Transactional email port (CLAUDE.md §9: provider abstraction) — every
 * caller (Better Auth's `sendResetPassword`/`sendVerificationEmail`,
 * `apps/api`'s invitation flow via its own mirror of this port) depends
 * on this shape, not on the Resend SDK, so swapping vendors later is a
 * one-file change here.
 *
 * Delivery failure never throws: without a verified sending domain,
 * Resend's sandbox only accepts the API key owner's own address, so a
 * signup/reset attempt for any other email is an *expected* delivery
 * failure, not a bug — it must not fail the auth flow that triggered it.
 */
export interface SendEmailInput {
  to: string;
  subject: string;
  body: string;
}

const resend = env.resendApiKey ? new Resend(env.resendApiKey) : null;

export async function sendEmail({ to, subject, body }: SendEmailInput): Promise<void> {
  if (!resend) {
    console.log(
      JSON.stringify({
        level: "info",
        logger: "email",
        message: "Email not delivered — RESEND_API_KEY not configured",
        to,
        subject,
        body,
      })
    );
    return;
  }

  try {
    const { error } = await resend.emails.send({
      from: env.resendFromEmail,
      to,
      subject,
      text: body,
    });
    if (error) {
      console.error(
        JSON.stringify({
          level: "error",
          logger: "email",
          message: "Resend delivery failed",
          to,
          subject,
          error,
        })
      );
    }
  } catch (err) {
    console.error(
      JSON.stringify({
        level: "error",
        logger: "email",
        message: "Resend delivery threw",
        to,
        subject,
        error: err instanceof Error ? err.message : String(err),
      })
    );
  }
}
