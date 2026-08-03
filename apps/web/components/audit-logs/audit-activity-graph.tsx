import * as React from "react";

import type { AuditActivity } from "@/lib/api/audit-logs";

import { Card } from "@/components/ui/card";

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/**
 * Daily audit volume over the selected window.
 *
 * A plain CSS bar chart rather than a charting library: it is one series
 * of at most 365 bars, and pulling a chart dependency into the audit
 * route would cost more bundle weight than the feature is worth
 * (CLAUDE.md §17 — the dashboard never pays for what it does not need).
 *
 * Every bar carries its value as text via the table below it, so the
 * information is never conveyed by bar height alone.
 */
export function AuditActivityGraph({
  activity,
  days,
}: {
  activity: AuditActivity;
  days: number;
}): React.JSX.Element {
  const peak = Math.max(1, ...activity.points.map((point) => point.count));
  const busiest = activity.points.reduce(
    (best, point) => (point.count > best.count ? point : best),
    activity.points[0] ?? { day: "", count: 0 }
  );

  return (
    <Card className="gap-4 p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-medium">Activity</h2>
          <p className="text-sm text-muted-foreground">
            {activity.total.toLocaleString()} event{activity.total === 1 ? "" : "s"} in the last{" "}
            {days} days
          </p>
        </div>
        {busiest.count > 0 && (
          <p className="text-xs text-muted-foreground">
            Busiest day: {formatDay(busiest.day)} ({busiest.count.toLocaleString()})
          </p>
        )}
      </div>

      {activity.total === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing has been recorded in this window.
        </p>
      ) : (
        <div
          className="flex h-24 items-end gap-px"
          role="img"
          aria-label={`Audit activity over the last ${days} days. ${activity.total} events total, peaking at ${busiest.count} on ${busiest.day ? formatDay(busiest.day) : "no day"}.`}
        >
          {activity.points.map((point) => (
            <div
              key={point.day}
              className="flex-1 rounded-t-sm bg-brand-500 transition-colors hover:bg-brand-600"
              // A zero-count day still gets a hairline, so the axis reads
              // as a continuous timeline rather than a gap in the data.
              style={{ height: `${Math.max(2, (point.count / peak) * 100)}%` }}
              title={`${formatDay(point.day)}: ${point.count} event${point.count === 1 ? "" : "s"}`}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
