import {
  Activity,
  Bell,
  BookOpen,
  Bot,
  CreditCard,
  KeyRound,
  LayoutDashboard,
  MessageSquare,
  Plug,
  ScrollText,
  Settings,
  Shield,
  Upload,
  Users,
  Users2,
  Workflow,
} from "lucide-react";

/**
 * The one navigation model — consumed by the sidebar, the command
 * palette, and the breadcrumb builder.
 *
 * Defined once rather than per-consumer so a route added to the sidebar
 * is automatically searchable in the palette and correctly labelled in
 * breadcrumbs. Three copies of this list drifting apart is exactly the
 * duplication Rule 3 exists to prevent.
 *
 * `pending` marks a section whose backend has not shipped: it is shown
 * and navigable (the AVDS sidebar structure is fixed), and the screen
 * itself renders its integration point rather than fake content.
 */

export interface NavItem {
  readonly label: string;
  readonly segment: string;
  readonly icon: React.ComponentType<{ className?: string }>;
  readonly description: string;
  readonly pending?: boolean;
  /** Hidden from the sidebar but still routable and palette-searchable. */
  readonly hiddenFromSidebar?: boolean;
}

export const NAV_SECTIONS: readonly NavItem[] = [
  {
    label: "Dashboard",
    segment: "",
    icon: LayoutDashboard,
    description: "Workspace overview, recent runs, and quick actions",
  },
  {
    label: "Agents",
    segment: "agents",
    icon: Bot,
    description: "Build, configure, publish, and run agents",
  },
  {
    label: "Playground",
    segment: "playground",
    icon: MessageSquare,
    description: "Test a published agent and watch it work live",
  },
  {
    label: "AI teams",
    segment: "teams",
    icon: Users2,
    description: "Multi-agent teams: supervisors, specialists, handoffs, and shared memory",
  },
  {
    label: "Knowledge",
    segment: "knowledge",
    icon: BookOpen,
    description: "Knowledge bases, documents, and retrieval testing",
  },
  {
    label: "Documents",
    segment: "documents",
    icon: ScrollText,
    description: "Every document across all knowledge bases",
    hiddenFromSidebar: true,
  },
  {
    label: "Upload",
    segment: "upload",
    icon: Upload,
    description: "Add documents to a knowledge base",
    hiddenFromSidebar: true,
  },
  {
    label: "MCP",
    segment: "mcp",
    icon: Plug,
    description: "Connect third-party MCP servers and their tools",
    pending: true,
  },
  {
    label: "Workflows",
    segment: "workflows",
    icon: Workflow,
    description: "Multi-step agent workflows on a DAG canvas",
    pending: true,
  },
  {
    label: "Analytics",
    segment: "analytics",
    icon: Activity,
    description: "Run volume, success rate, latency, and cost over time",
    pending: true,
  },
  {
    label: "Members",
    segment: "team",
    icon: Users,
    // Deliberately *not* labelled "Team": `/teams` is teams of agents,
    // `/team` is human workspace membership. Two sidebar entries both
    // reading "Team" would be a coin flip for the user every time.
    description: "Workspace members (people) and their roles",
  },
  {
    label: "Billing",
    segment: "billing",
    icon: CreditCard,
    description: "Subscription, usage against quota, and invoices",
    pending: true,
  },
  {
    label: "Settings",
    segment: "settings",
    icon: Settings,
    description: "Workspace, security, API keys, and preferences",
  },
  {
    label: "API keys",
    segment: "settings/api-keys",
    icon: KeyRound,
    description: "Issue and revoke workspace-scoped API keys",
    hiddenFromSidebar: true,
  },
  {
    label: "Security",
    segment: "settings/security",
    icon: Shield,
    description: "Session, access control, and audit trail",
    hiddenFromSidebar: true,
  },
  {
    label: "Integrations",
    segment: "integrations",
    icon: Plug,
    description: "Authorise third-party services for this workspace",
    hiddenFromSidebar: true,
    pending: true,
  },
  {
    label: "Audit logs",
    segment: "audit-logs",
    icon: ScrollText,
    description: "Append-only record of authentication and destructive actions",
    hiddenFromSidebar: true,
    pending: true,
  },
  {
    label: "Notifications",
    segment: "notifications",
    icon: Bell,
    description: "Failed runs, quota thresholds, and invitations",
    hiddenFromSidebar: true,
    pending: true,
  },
];

export function hrefFor(workspaceId: string, segment: string): string {
  return segment ? `/dashboard/${workspaceId}/${segment}` : `/dashboard/${workspaceId}`;
}

/** Sidebar shows the fixed AVDS sections; deep routes stay palette-only. */
export const SIDEBAR_SECTIONS = NAV_SECTIONS.filter((item) => !item.hiddenFromSidebar);
