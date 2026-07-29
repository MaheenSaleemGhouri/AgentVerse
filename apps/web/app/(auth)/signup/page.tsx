import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { enabledSocialProviders } from "@/lib/social-providers";

export const metadata: Metadata = {
  title: "Sign up — AgentVerse",
  description: "Create your AgentVerse account — the AI Workforce Operating System.",
};

export default function SignupPage(): React.JSX.Element {
  return <AuthShell active="signup" socialProviders={enabledSocialProviders()} />;
}
