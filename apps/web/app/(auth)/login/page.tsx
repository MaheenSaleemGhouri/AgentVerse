import type { Metadata } from "next";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Log in — AgentVerse" };

export default function LoginPage(): React.JSX.Element {
  // Server Component: reads server-only env directly, no NEXT_PUBLIC_*
  // variable needed just to know whether GitHub OAuth is configured.
  const githubEnabled = Boolean(process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET);

  return <LoginForm githubEnabled={githubEnabled} />;
}
