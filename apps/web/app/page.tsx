import Link from "next/link";

/**
 * Still a placeholder — the marketing/landing page is a later phase
 * (docs/roadmap.md). Updated in Phase 1 only to link to the now-real
 * login/signup flow instead of claiming no product surface exists.
 */
export default function HomePage(): React.JSX.Element {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold">AgentVerse</h1>
      <p className="max-w-md text-sm text-neutral-500 dark:text-neutral-400">
        Build, deploy, and orchestrate AI agents and multi-agent systems.
      </p>
      <div className="flex gap-3">
        <Link
          href="/signup"
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Sign up
        </Link>
        <Link
          href="/login"
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
        >
          Log in
        </Link>
      </div>
      {/* Quiet text links rather than more buttons: both are public
          surfaces someone reads *before* deciding to sign up, so they
          have to be reachable without an account — but neither is the
          action this page is asking for. */}
      <div className="flex gap-4 text-sm text-neutral-500 dark:text-neutral-400">
        <Link href="/docs" className="hover:text-foreground hover:underline">
          Documentation
        </Link>
        <Link href="/pricing" className="hover:text-foreground hover:underline">
          Pricing
        </Link>
      </div>
    </main>
  );
}
