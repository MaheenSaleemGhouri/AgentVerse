import {
  Activity,
  Bell,
  BookOpen,
  Bot,
  CreditCard,
  HelpCircle,
  KeyRound,
  LayoutDashboard,
  LifeBuoy,
  MessageSquare,
  Plug,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Store,
  Terminal,
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
    label: "Marketplace",
    segment: "marketplace",
    icon: Store,
    description: "Install first-party templates and community agents, and publish your own",
  },
  {
    label: "MCP",
    segment: "mcp",
    icon: Activity,
    description: "Tool-call history across every integration, including refused calls",
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
    description: "Subscription, usage against quota, credit, and invoices",
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
    label: "API explorer",
    segment: "settings/api-explorer",
    icon: Terminal,
    description: "Try API requests against this workspace and copy the code",
    hiddenFromSidebar: true,
  },
  {
    label: "Your listings",
    segment: "marketplace/my-listings",
    icon: Store,
    description: "Marketplace listings you publish — drafts, reviews, and versions",
    hiddenFromSidebar: true,
  },
  {
    label: "Integrations",
    segment: "integrations",
    icon: Plug,
    description: "Connect external services through MCP and manage their credentials",
    hiddenFromSidebar: true,
  },
  {
    label: "Audit logs",
    segment: "audit-logs",
    icon: ScrollText,
    description: "Append-only record of authentication and destructive actions",
    hiddenFromSidebar: true,
  },
  {
    label: "Notifications",
    segment: "notifications",
    icon: Bell,
    description: "Billing events, quota thresholds, and referral rewards",
    hiddenFromSidebar: true,
  },
  {
    label: "Notification preferences",
    segment: "settings/notifications",
    icon: Bell,
    description: "Choose which notification categories arrive by email vs. in-app only",
    hiddenFromSidebar: true,
    pending: true,
  },
  {
    label: "Help center",
    segment: "help",
    icon: HelpCircle,
    description: "Guides, documentation, and how to reach support",
    hiddenFromSidebar: true,
  },
  {
    label: "Support",
    segment: "support",
    icon: LifeBuoy,
    description: "File a ticket and an agent triages it — category, priority, and a draft reply",
    // Dogfooding tooling (Phase 11), not a customer-facing pillar the
    // fixed AVDS sidebar structure needs a permanent slot for — routable
    // and palette-searchable like Integrations/Audit logs above.
    hiddenFromSidebar: true,
  },
  {
    label: "Marketplace moderation",
    segment: "admin/marketplace",
    icon: ShieldCheck,
    description: "Platform staff: review listings submitted for publication",
    // Hidden from the sidebar like every other deep route, and the page
    // itself 404s for anyone who is not platform staff. Being palette-
    // searchable does not grant anything — the API is the gate.
    hiddenFromSidebar: true,
  },
];

export function hrefFor(workspaceId: string, segment: string): string {
  return segment ? `/dashboard/${workspaceId}/${segment}` : `/dashboard/${workspaceId}`;
}

/** Sidebar shows the fixed AVDS sections; deep routes stay palette-only. */
export const SIDEBAR_SECTIONS = NAV_SECTIONS.filter((item) => !item.hiddenFromSidebar);
