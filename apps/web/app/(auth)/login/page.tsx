import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { enabledSocialProviders } from "@/lib/social-providers";
import { ssoLoginOptions } from "@/lib/sso-login-options";

export const metadata: Metadata = {
  title: "Log in — AgentVerse",
  description: "Log in to AgentVerse — the AI Workforce Operating System.",
};

export default async function LoginPage(): Promise<React.JSX.Element> {
  // Server Component: reads the server-only secrets directly, so no
  // NEXT_PUBLIC_* mirror is needed just to know which OAuth buttons are
  // usable (§10 audits every NEXT_PUBLIC_ addition — it ships to the
  // browser, and this decision does not need to).
  //
  // The Suspense boundary LoginForm's useSearchParams() needs lives in
  // AuthShell, next to the component that requires it.
  return (
    <AuthShell
      active="login"
      socialProviders={enabledSocialProviders()}
      ssoOptions={await ssoLoginOptions()}
    />
  );
}
