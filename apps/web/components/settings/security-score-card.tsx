import { ShieldCheck } from "lucide-react";
import * as React from "react";

import type { SecurityScore } from "@/lib/api/security";
import { cn } from "@/lib/utils";

import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/** Grade drives the accent colour, but never carries the meaning alone —
 *  the grade letter and the numeric score are always shown as text too
 *  (WCAG 2.2 AA: status is never colour-only). */
function toneForGrade(grade: string): string {
  if (grade === "A" || grade === "B") return "text-success";
  if (grade === "C") return "text-warning";
  return "text-destructive";
}

/**
 * The workspace's security posture, out of 100, with the breakdown that
 * produced it.
 *
 * The factors are not decoration: a bare score tells an admin they have
 * a problem without telling them which one, so every line that lost
 * points carries the specific remediation the API computed.
 */
export function SecurityScoreCard({ score }: { score: SecurityScore }): React.JSX.Element {
  return (
    <Card className="gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <ShieldCheck className="size-4.5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="font-medium">Security score</h2>
            <p className="text-sm text-muted-foreground">
              Computed from this workspace&apos;s actual configuration, not a checklist.
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className={cn("text-2xl font-semibold tabular-nums", toneForGrade(score.grade))}>
            {score.score}
            <span className="text-sm text-muted-foreground">/100</span>
          </div>
          <div className="text-xs text-muted-foreground">Grade {score.grade}</div>
        </div>
      </div>

      <Separator />

      <ul className="space-y-3">
        {score.factors.map((factor) => {
          const complete = factor.earned === factor.possible;
          return (
            <li key={factor.key} className="space-y-1">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span>{factor.label}</span>
                <span
                  className={cn(
                    "shrink-0 tabular-nums",
                    complete ? "text-success" : "text-muted-foreground"
                  )}
                >
                  {factor.earned}/{factor.possible}
                </span>
              </div>
              <div
                className="h-1 overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${factor.label}: ${factor.earned} of ${factor.possible} points`}
              >
                <div
                  className={cn("h-full rounded-full", complete ? "bg-success" : "bg-warning")}
                  style={{
                    width: `${factor.possible === 0 ? 0 : (factor.earned / factor.possible) * 100}%`,
                  }}
                />
              </div>
              {factor.remediation ? (
                <p className="text-xs text-muted-foreground">{factor.remediation}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
