import { ArrowRight, Mail, Search } from "lucide-react";
import Link from "next/link";

import { PILLARS } from "@/lib/docs/pillars";

import { AgentVerseMascot } from "@/components/brand/agentverse-mascot";
import { PageHeader } from "@/components/patterns/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Help center — search and browse the real documentation, plus an
 * honest statement of the one real contact channel that exists.
 *
 * There is no live-chat widget, ticketing system, or general support
 * mailbox configured anywhere in the codebase (`sales@agentverse.dev`
 * is Enterprise sales, used on the pricing and billing pages — reusing
 * it here as "contact support" would misrepresent what it is). So this
 * page names that plainly rather than presenting a chat bubble that
 * goes nowhere.
 */
export default function HelpCenterPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Help center"
        description="Guides for every part of AgentVerse, organized the way you'd look for them."
      />

      <Card className="gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <AgentVerseMascot pose="happy" className="hidden h-16 w-auto sm:block" />
          <div className="space-y-1">
            <p className="font-medium text-foreground">Search the documentation</p>
            <p className="text-sm text-muted-foreground">
              Every guide, indexed and searchable — build an agent, connect a tool, read a trace,
              call the API.
            </p>
          </div>
        </div>
        <Button asChild>
          <Link href="/docs">
            <Search className="size-4" />
            Open documentation
          </Link>
        </Button>
      </Card>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Browse by topic</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PILLARS.map((pillar) => (
            <Card key={pillar.slug} className="gap-2">
              <CardHeader>
                <CardTitle className="text-base">{pillar.name}</CardTitle>
                <CardDescription>{pillar.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <Link
                  href={`/docs#pillar-${pillar.slug}`}
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                >
                  View guides
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Card className="gap-2 p-6">
        <p className="font-medium text-foreground">Still stuck?</p>
        <p className="max-w-2xl text-sm text-muted-foreground">
          AgentVerse doesn&apos;t have a general support inbox or live chat set up yet — the
          documentation above is the most current source. For enterprise or sales questions,
          reach the team directly.
        </p>
        <div>
          <Button variant="outline" asChild className="mt-1">
            <a href="mailto:sales@agentverse.dev">
              <Mail className="size-4" />
              Contact sales
            </a>
          </Button>
        </div>
      </Card>
    </div>
  );
}

export const metadata = {
  title: "Help center · AgentVerse",
};
