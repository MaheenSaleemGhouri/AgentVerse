import Link from "next/link";
import * as React from "react";

import { DocsSearch } from "@/components/docs/docs-search";
import { DocsSidebar } from "@/components/docs/docs-sidebar";
import { loadNav } from "@/lib/docs/loader";
import { buildDocsSearchIndex } from "@/lib/docs/search-index";

/**
 * The documentation shell.
 *
 * Public and unauthenticated — docs are a surface someone reads while
 * deciding whether to sign up, so they must be readable and indexable
 * without an account. Both the sidebar and the search index come from
 * the same corpus the pages render, so adding a `.md` file updates all
 * three with no registry to keep in step.
 */
export default async function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.JSX.Element> {
  const [sections, searchIndex] = await Promise.all([loadNav(), buildDocsSearchIndex()]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-6">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            AgentVerse
          </Link>
          <span className="text-sm text-muted-foreground">Docs</span>
          <div className="ml-auto w-full max-w-xs">
            <DocsSearch index={searchIndex} />
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-10 px-6 py-10">
        {/* Below `lg` the sidebar is hidden rather than collapsed into a
            drawer: search is in the header at every width, and it is the
            faster route to a guide than a list of forty links. */}
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="sticky top-24">
            <DocsSidebar
              sections={sections.map((section) => ({
                slug: section.slug,
                name: section.name,
                guides: section.guides.map((guide) => ({
                  slug: guide.slug,
                  title: guide.title,
                })),
              }))}
            />
          </div>
        </aside>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
