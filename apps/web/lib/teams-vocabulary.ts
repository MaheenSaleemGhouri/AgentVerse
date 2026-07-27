import {
  Boxes,
  Braces,
  ClipboardList,
  GitBranch,
  ListOrdered,
  Merge,
  PenLine,
  Search,
  ShieldCheck,
  Split,
  UserCog,
  Wrench,
} from "lucide-react";

import type { TeamRole, Topology } from "@/lib/api/teams";

/**
 * The one place topologies and roles are described for humans.
 *
 * Defined once rather than per-screen so the teams list, the builder,
 * and the runtime view cannot describe the same topology three
 * different ways. Icons come from lucide only (senior-ui-designer: one
 * icon set, consistent stroke).
 */

export interface TopologyMeta {
  readonly label: string;
  readonly icon: React.ComponentType<{ className?: string }>;
  readonly summary: string;
  /** What the user has to configure for this topology to be runnable. */
  readonly requires: string;
}

/**
 * `satisfies` rather than a `Record<Topology, …>` annotation: under
 * `noUncheckedIndexedAccess` an annotated Record yields `T | undefined`
 * on every lookup, forcing a `??` fallback at each call site that could
 * never fire. `satisfies` keeps the keys literal — exhaustiveness is
 * still checked, and lookups are known-present.
 */
export const TOPOLOGIES = {
  supervisor_worker: {
    label: "Supervisor / worker",
    icon: UserCog,
    summary: "A supervisor decides which specialist to delegate each part of the task to.",
    requires: "A supervisor, plus at least one other member it can hand off to.",
  },
  planner_executor_critic: {
    label: "Planner / executor / critic",
    icon: ClipboardList,
    summary: "One plans, one carries it out, one reviews and corrects the result.",
    requires: "Exactly one planner, one executor, and one critic.",
  },
  sequential: {
    label: "Sequential",
    icon: ListOrdered,
    summary: "Members run in order, each picking up where the previous one finished.",
    requires: "At least one member. Drag to set the order they run in.",
  },
  parallel: {
    label: "Parallel",
    icon: Split,
    summary: "Members work the same task at once, then an aggregator merges their answers.",
    requires: "At least one member besides the aggregator.",
  },
} satisfies Record<Topology, TopologyMeta>;

export interface RoleMeta {
  readonly label: string;
  readonly icon: React.ComponentType<{ className?: string }>;
  readonly summary: string;
}

export const TEAM_ROLES = {
  supervisor: {
    label: "Supervisor",
    icon: UserCog,
    summary: "Plans the work and delegates to the rest of the team.",
  },
  planner: { label: "Planner", icon: ClipboardList, summary: "Breaks the task into steps." },
  executor: { label: "Executor", icon: Wrench, summary: "Carries out the plan." },
  critic: {
    label: "Critic",
    icon: ShieldCheck,
    summary: "Reviews the work and gives the corrected answer.",
  },
  researcher: { label: "Researcher", icon: Search, summary: "Gathers and verifies information." },
  coder: { label: "Coder", icon: Braces, summary: "Writes and reviews code." },
  writer: { label: "Writer", icon: PenLine, summary: "Produces the written output." },
  worker: { label: "Worker", icon: Boxes, summary: "General-purpose team member." },
  aggregator: {
    label: "Aggregator",
    icon: Merge,
    summary: "Merges parallel members' output into one answer.",
  },
} satisfies Record<TeamRole, RoleMeta>;

/** Role keys in the order the builder offers them. */
export const ROLE_ORDER = [
  "supervisor",
  "planner",
  "executor",
  "critic",
  "researcher",
  "coder",
  "writer",
  "worker",
  "aggregator",
] as const satisfies readonly TeamRole[];

export interface HandoffKindMeta {
  readonly label: string;
  readonly tone: "brand" | "info" | "neutral" | "warning";
  readonly explanation: string;
}

/**
 * "The model chose this" and "the topology dictated this" are different
 * facts when debugging a badly-routed run, which is why the backend
 * records them distinctly — and why the UI must not collapse them into
 * one generic "handoff" chip.
 */
export const HANDOFF_KINDS: Record<string, HandoffKindMeta> = {
  automatic: {
    label: "Automatic",
    tone: "brand",
    explanation: "The supervisor agent chose to delegate this.",
  },
  manual: {
    label: "Sequenced",
    tone: "info",
    explanation: "The topology moved to the next member.",
  },
  conditional: {
    label: "Conditional",
    tone: "warning",
    explanation: "A configured condition routed this.",
  },
  parallel: {
    label: "Parallel",
    tone: "neutral",
    explanation: "A parallel branch finished and reported back.",
  },
};

export const COMMUNICATION_KINDS: Record<string, { label: string; icon: typeof GitBranch }> = {
  task_request: { label: "Task request", icon: GitBranch },
  task_result: { label: "Task result", icon: ClipboardList },
  context_share: { label: "Context shared", icon: Boxes },
  intermediate_result: { label: "Intermediate result", icon: Merge },
  error_report: { label: "Error reported", icon: ShieldCheck },
};

/** Session status → the shared status vocabulary's tone. */
export function sessionTone(status: string): "neutral" | "info" | "success" | "danger" {
  switch (status) {
    case "queued":
      return "neutral";
    case "running":
      return "info";
    case "success":
      return "success";
    default:
      return "danger";
  }
}
