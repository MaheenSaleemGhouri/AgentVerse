import "server-only";

/**
 * Transactional email port (Increment 5 decision, confirmed with the
 * project owner: ship the invite/accept and password-reset flows as
 * real and testable today, behind a dev-only stub that logs instead of
 * delivering — no vendor is configured yet). Every caller (Better Auth's
 * `sendResetPassword`, `apps/api`'s invitation flow via its own mirror
 * of this port) depends on this shape, not on a vendor SDK — swapping in
 * Resend/SES/SMTP later is a one-file change here, no caller changes
 * (CLAUDE.md §9: provider abstraction).
 */
export interface SendEmailInput {
  to: string;
  subject: string;
  body: string;
}

export async function sendEmail({ to, subject, body }: SendEmailInput): Promise<void> {
  console.log(
    JSON.stringify({
      level: "info",
      logger: "email",
      message: "Email not delivered — no transactional email vendor configured yet",
      to,
      subject,
      body,
    })
  );
}
