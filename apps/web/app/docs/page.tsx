import type { Metadata } from "next";
import Link from "next/link";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { loadNav } from "@/lib/docs/loader";

export const metadata: Metadata = {
  title: "Documentation · AgentVerse",
  description:
    "Guides for building, running and operating AI agents on AgentVerse — the agent builder, orchestration, observability, the marketplace, and the platform API, SDKs and CLI.",
};

export default async function DocsIndexPage(): Promise<React.JSX.Element> {
  const sections = await loadNav();

  return (
    <div className="max-w-3xl">
      <h1 className="text-3xl font-semibold tracking-tight">Documentation</h1>
      <p className="mt-3 text-muted-foreground">
        How to build an agent, connect it to tools, run it, watch what it did, and ship it. Every
        guide here is written against the shipped product.
      </p>

      <div className="mt-10 space-y-10">
        {sections.map((section) => (
          <section key={section.slug} aria-labelledby={`pillar-${section.slug}`}>
            <h2 id={`pillar-${section.slug}`} className="text-lg font-semibold tracking-tight">
              {section.name}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">{section.description}</p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {section.guides.map((guide) => (
                <Card key={guide.slug} className="p-0">
                  <Link
                    href={`/docs/${guide.slug}`}
                    className="block h-full rounded-lg p-4 transition-colors hover:bg-accent/50"
                  >
                    <span className="block text-sm font-medium">{guide.title}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {guide.summary}
                    </span>
                  </Link>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
