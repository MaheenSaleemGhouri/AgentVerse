import type { Metadata } from "next";
import { notFound } from "next/navigation";
import * as React from "react";

import { TableOfContents } from "@/components/docs/table-of-contents";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { findGuide, loadPublishedGuides } from "@/lib/docs/loader";
import { pillarBySlug } from "@/lib/docs/pillars";
import { renderMarkdown } from "@/lib/docs/render";

interface PageProps {
  params: Promise<{ slug: string[] }>;
}

/**
 * Enumerated from the corpus, so every published guide is prerendered at
 * build time and no guide is reachable that the sidebar does not list.
 *
 * These pages really are static HTML (`● (SSG)` in the build output),
 * unlike `/pricing` and `/login` — those sit under layouts that fetch
 * SSO providers per request, which opts them out of static generation.
 * The docs shell deliberately fetches nothing per-request, which is what
 * keeps that from happening here.
 */
export async function generateStaticParams(): Promise<{ slug: string[] }[]> {
  const guides = await loadPublishedGuides();
  return guides.map((guide) => ({ slug: guide.slug.split("/") }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const guide = await findGuide(slug.join("/"));
  if (!guide) return { title: "Not found · AgentVerse Docs" };

  return {
    title: `${guide.title} · AgentVerse Docs`,
    description: guide.summary,
    alternates: { canonical: `/docs/${guide.slug}` },
    openGraph: {
      title: guide.title,
      description: guide.summary,
      type: "article",
    },
  };
}

export default async function GuidePage({ params }: PageProps): Promise<React.JSX.Element> {
  const { slug } = await params;
  const guide = await findGuide(slug.join("/"));
  if (!guide) notFound();

  const html = await renderMarkdown(guide.body);
  const pillar = pillarBySlug(guide.pillar);

  return (
    <div className="flex gap-10">
      <article className="min-w-0 max-w-3xl flex-1">
        <p className="text-sm text-muted-foreground">{pillar?.name ?? guide.pillar}</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{guide.title}</h1>
        <p className="mt-3 text-muted-foreground">{guide.summary}</p>

        {guide.status === "deprecated" && (
          <Alert tone="warning" className="mt-6">
            <AlertTitle>This guide is deprecated</AlertTitle>
            <AlertDescription>
              It describes a flow that is being retired. Follow the related guides below for the
              current approach.
            </AlertDescription>
          </Alert>
        )}

        {/* Rendered from markdown this repository authors and builds —
            not from user input, and not fetched at runtime. The whole
            corpus is on disk and reviewed in the same pull request as
            the code, which is what makes setting it as HTML safe here
            and would not make it safe anywhere it came from a request. */}
        <div className="docs-prose mt-8" dangerouslySetInnerHTML={{ __html: html }} />

        <footer className="mt-16 border-t border-border pt-6 text-sm text-muted-foreground">
          Last verified against the product on{" "}
          <time dateTime={guide.last_verified}>{guide.last_verified}</time>.
        </footer>

        {/* Generated server-side from the same frontmatter the page
            renders, so the structured data cannot describe a different
            article from the one a reader sees. */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "TechArticle",
              headline: guide.title,
              description: guide.summary,
              dateModified: guide.last_verified,
              articleSection: pillar?.name ?? guide.pillar,
              isPartOf: {
                "@type": "WebSite",
                name: "AgentVerse Documentation",
              },
            }),
          }}
        />
      </article>

      <aside className="hidden w-56 shrink-0 xl:block">
        <div className="sticky top-24">
          <TableOfContents headings={guide.headings} />
        </div>
      </aside>
    </div>
  );
}
