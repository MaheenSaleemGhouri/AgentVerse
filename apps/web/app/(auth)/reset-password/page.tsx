import type { Metadata } from "next";
import { Suspense } from "react";

import { ResetPasswordForm } from "./reset-password-form";

export const metadata: Metadata = {
  title: "Set a new password — AgentVerse",
  description: "Finish resetting your AgentVerse password.",
};

export default function ResetPasswordPage(): React.JSX.Element {
  // Suspense boundary for ResetPasswordForm's useSearchParams() (reads
  // the `?token=` Better Auth redirects here with), the same requirement
  // login-form.tsx's AuthShell satisfies for its own useSearchParams().
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
