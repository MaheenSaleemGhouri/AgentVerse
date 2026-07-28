import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Clock,
  Database,
  Globe,
  KeyRound,
  MessageSquare,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  Users,
  Zap,
} from "lucide-react";

import type {
  Availability,
  Health,
  InstallStatus,
  PermissionLevel,
  ToolCallStatus,
  Transport,
} from "@/lib/api/integrations";

/**
 * How integration concepts are described to humans, defined once so the
 * marketplace, the detail page, and the runtime view cannot describe the
 * same state three different ways.
 *
 * `satisfies` rather than an annotated `Record`: under
 * `noUncheckedIndexedAccess` an annotated Record yields `T | undefined`
 * on every lookup, forcing a `??` fallback at each call site that could
 * never fire.
 */

export const TRANSPORTS = {
  stdio: {
    label: "Local process",
    icon: Terminal,
    summary:
      "Runs as a process next to the worker. Only available for servers AgentVerse has vetted.",
  },
  sse: {
    label: "Server-sent events",
    icon: Globe,
    summary: "A remote server, reached through the egress control point.",
  },
  streamable_http: {
    label: "Streamable HTTP",
    icon: Globe,
    summary: "A remote server, reached through the egress control point.",
  },
} satisfies Record<Transport, { label: string; icon: typeof Globe; summary: string }>;

export const AVAILABILITY = {
  official: {
    label: "Official",
    tone: "success" as const,
    summary: "Published and maintained by the vendor.",
  },
  community: {
    label: "Community",
    tone: "info" as const,
    summary: "Built by a third party. Useful, but nobody is contractually on the hook for it.",
  },
  custom_required: {
    label: "No server yet",
    tone: "neutral" as const,
    // The honest one. A card that could not be installed and did not say
    // why would be worse than no card at all.
    summary:
      "No MCP server exists for this service today. Register your own endpoint to connect it.",
  },
} satisfies Record<
  Availability,
  { label: string; tone: "success" | "info" | "neutral"; summary: string }
>;

export const INSTALL_STATUS = {
  pending_auth: {
    label: "Needs credentials",
    tone: "warning" as const,
    icon: KeyRound,
    summary: "Add the credentials this server needs before agents can use it.",
  },
  active: {
    label: "Active",
    tone: "success" as const,
    icon: CheckCircle2,
    summary: "Available to any agent it has been granted to.",
  },
  disabled: {
    label: "Disabled",
    tone: "neutral" as const,
    icon: CircleSlash,
    summary: "Its tools are not offered. Configuration and credentials are kept.",
  },
  error: {
    label: "Error",
    tone: "danger" as const,
    icon: AlertTriangle,
    summary: "Something went wrong on the last attempt to use this server.",
  },
} satisfies Record<
  InstallStatus,
  {
    label: string;
    tone: "warning" | "success" | "neutral" | "danger";
    icon: typeof KeyRound;
    summary: string;
  }
>;

export const HEALTH = {
  healthy: { label: "Healthy", tone: "success" as const },
  degraded: { label: "Degraded", tone: "warning" as const },
  unreachable: { label: "Unreachable", tone: "danger" as const },
  unknown: { label: "Not checked", tone: "neutral" as const },
} satisfies Record<
  Health,
  { label: string; tone: "success" | "warning" | "danger" | "neutral" }
>;

export const PERMISSION_LEVELS = {
  read_only: {
    label: "Read only",
    icon: ShieldCheck,
    // Stated plainly because it is the guarantee the user is relying on.
    summary: "The agent can read, never write. Tools that change data are refused.",
  },
  read_write: {
    label: "Read and write",
    icon: Zap,
    summary: "The agent can change data on the connected service.",
  },
  admin: {
    label: "Admin",
    icon: Users,
    summary: "Full access, including the server's administrative tools.",
  },
} satisfies Record<
  PermissionLevel,
  { label: string; icon: typeof ShieldCheck; summary: string }
>;

export const CALL_STATUS = {
  success: { label: "Success", tone: "success" as const, icon: CheckCircle2 },
  error: { label: "Failed", tone: "danger" as const, icon: AlertTriangle },
  timeout: { label: "Timed out", tone: "warning" as const, icon: Clock },
  // A denial is the system working, not a fault — toned as a warning
  // rather than an error so a wall of legitimate refusals does not read
  // as an outage.
  denied: { label: "Denied", tone: "warning" as const, icon: Ban },
  circuit_open: { label: "Server paused", tone: "neutral" as const, icon: CircleDashed },
  cached: { label: "Cached", tone: "info" as const, icon: Sparkles },
} satisfies Record<
  ToolCallStatus,
  {
    label: string;
    tone: "success" | "danger" | "warning" | "neutral" | "info";
    icon: typeof CheckCircle2;
  }
>;

export const CATEGORY_ICONS: Record<string, typeof Server> = {
  "Developer tools": Terminal,
  Communication: MessageSquare,
  Productivity: Sparkles,
  Business: Users,
  Data: Database,
  Cloud: Globe,
  Infrastructure: Server,
};

export const CATEGORIES = [
  "Developer tools",
  "Communication",
  "Productivity",
  "Business",
  "Data",
  "Cloud",
  "Infrastructure",
] as const;
