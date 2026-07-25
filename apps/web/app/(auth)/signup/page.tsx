import type { Metadata } from "next";

import { SignupForm } from "./signup-form";

export const metadata: Metadata = { title: "Sign up — AgentVerse" };

export default function SignupPage(): React.JSX.Element {
  const githubEnabled = Boolean(process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET);

  return <SignupForm githubEnabled={githubEnabled} />;
}
