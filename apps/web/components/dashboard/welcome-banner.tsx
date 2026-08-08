import * as React from "react";

import { AgentVerseMascot } from "@/components/brand/agentverse-mascot";
import { Card } from "@/components/ui/card";

/**
 * The dashboard's opening line.
 *
 * The one place on this screen the mascot appears. It belongs here and
 * nowhere else on the page: a greeting is the moment the product has a
 * voice, and every other panel is operational data the mascot would only
 * get in the way of (docs/design/design-system.md §6 — "use it
 * intentionally").
 *
 * `aria-hidden` on the mascot, because the greeting beside it already
 * says everything the illustration does.
 */
export function WelcomeBanner({
  greeting,
  workspaceName,
  status,
}: {
  greeting: string;
  workspaceName: string;
  /** One honest sentence about where the workspace stands. */
  status: string;
}): React.JSX.Element {
  return (
    <Card className="relative gap-0 overflow-hidden border-border bg-accent/40 p-6 sm:p-7">
      <div className="relative z-10 max-w-2xl">
        <h1 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
          {greeting}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Here&apos;s where <span className="font-medium text-foreground">{workspaceName}</span>{" "}
          stands right now. {status}
        </p>
      </div>

      {/* Hidden below `sm`: on a phone the greeting and the first stat
          card matter more than the illustration, and squeezing both in
          shrinks the mascot to an unrecognisable smudge. */}
      <AgentVerseMascot
        pose="waving"
        className="pointer-events-none absolute -right-2 bottom-0 hidden h-[120%] w-auto opacity-90 sm:block"
      />
    </Card>
  );
}
