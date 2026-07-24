/**
 * Phase 0 placeholder. This route intentionally ships no product UI —
 * the agent builder, dashboards, and marketplace land in later phases
 * (docs/roadmap.md). Its only job here is to prove the Next.js 15 App
 * Router shell renders, so CI's build stage has something real to build.
 */
export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-2xl font-semibold">AgentVerse</h1>
      <p className="max-w-md text-sm text-neutral-500 dark:text-neutral-400">
        Engineering foundation — Phase 0. Product surfaces begin in Phase 1.
      </p>
    </main>
  );
}
