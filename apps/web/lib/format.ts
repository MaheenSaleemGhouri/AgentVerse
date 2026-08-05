/**
 * Display formatting shared across every screen.
 *
 * Lives in `lib/` rather than inline in JSX (CLAUDE.md §6: derived
 * calculations are never inline in components), and is written by hand
 * rather than pulling a date library in — these are four small pure
 * functions against a well-defined input, and each is unit-testable.
 */

/** Money is integer micro-USD end to end (Rule 15); only display converts. */
export function formatMicroUsd(microUsd: number): string {
  const usd = microUsd / 1_000_000;
  // Sub-cent costs are the norm for a single run, so 4dp below a cent
  // and 2dp above it — a run showing "$0.00" would look free.
  return usd < 0.01 && usd > 0 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

const RELATIVE_UNITS: ReadonlyArray<{ limit: number; divisor: number; unit: Intl.RelativeTimeFormatUnit }> = [
  { limit: 60, divisor: 1, unit: "second" },
  { limit: 3600, divisor: 60, unit: "minute" },
  { limit: 86400, divisor: 3600, unit: "hour" },
  { limit: 604800, divisor: 86400, unit: "day" },
  { limit: 2629800, divisor: 604800, unit: "week" },
  { limit: 31557600, divisor: 2629800, unit: "month" },
];

/**
 * "3 minutes ago". Uses `Intl.RelativeTimeFormat` so the wording is
 * locale-correct rather than a hand-built English-only string.
 */
export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";

  const seconds = Math.round((then - Date.now()) / 1000);
  const absolute = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  for (const { limit, divisor, unit } of RELATIVE_UNITS) {
    if (absolute < limit) return formatter.format(Math.round(seconds / divisor), unit);
  }
  return formatter.format(Math.round(seconds / 31557600), "year");
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/** Duration between two ISO timestamps, for run wall-clock time. */
export function formatDuration(startIso: string, endIso: string | null): string {
  if (!endIso) return "—";
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  if (Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

/** Two-letter monogram for an avatar fallback. */
export function initialsFrom(value: string): string {
  const parts = value.trim().split(/[\s@._-]+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "?";
  const second = parts.length > 1 ? (parts[1]?.[0] ?? "") : "";
  return (first + second).toUpperCase();
}

/**
 * Customer-facing money is integer cents (Rule 15); only display
 * converts. Separate from `formatMicroUsd` on purpose — that one is
 * per-LLM-call platform cost at sub-cent precision, this one is a price
 * or an invoice line, and showing a price to four decimal places would
 * read as a bug.
 */
export function formatCents(cents: number, currency = "usd"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

/**
 * A metered dimension's key as a human label: `agent_runs` ->
 * "Agent runs". Derived rather than kept as a lookup table so a new
 * backend dimension renders sensibly the day it ships instead of falling
 * back to a raw key.
 */
export function humanizeDimension(dimension: string): string {
  const spaced = dimension.replace(/_/g, " ");
  const label = spaced.charAt(0).toUpperCase() + spaced.slice(1);
  // `mb` and `mcp` read as words otherwise.
  return label.replace(/\bmb\b/g, "MB").replace(/\bmcp\b/g, "MCP").replace(/\bapi\b/g, "API");
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(date);
}
