import type { Metadata } from "next";

import { ForgotPasswordForm } from "./forgot-password-form";

export const metadata: Metadata = {
  title: "Reset password — AgentVerse",
  description: "Recover access to your AgentVerse account.",
};

/**
 * The destination of the login panel's "Forgot password?" control.
 *
 * Increment 5 wires `emailAndPassword.sendResetPassword` (see
 * `lib/auth.ts`) to a dev-only logging sender (`lib/email/sender.ts`) —
 * no vendor is configured yet, so the reset link is written to the
 * server log rather than delivered to an inbox. The flow itself (token
 * generation, expiry, single-use consumption, this form, the
 * `/reset-password` completion page) is real and exercised end-to-end;
 * only actual delivery is stubbed, and swapping in a vendor later is a
 * one-file change behind `lib/email/sender.ts`, not a change to this page.
 */
export default function ForgotPasswordPage(): React.JSX.Element {
  return <ForgotPasswordForm />;
}
