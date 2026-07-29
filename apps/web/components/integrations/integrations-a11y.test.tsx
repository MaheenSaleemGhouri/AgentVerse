/**
 * WCAG 2.2 AA regression gate for the Phase 6 integration surfaces
 * (CLAUDE.md §15, Rule 7 — accessibility is a merge gate, not a
 * follow-up).
 *
 * axe-core runs against each component's real rendered output. This
 * catches the mechanical failures — missing accessible names, unlabelled
 * controls, broken heading/list structure, ARIA misuse — so that a
 * regression fails CI rather than reaching a keyboard user.
 *
 * What it deliberately does NOT claim: axe detects a minority of real
 * accessibility problems. The manual keyboard and screen-reader passes
 * recorded in docs/accessibility/phase-6-audit.md are what cover focus
 * order, live-region verbosity, and whether the flow is actually usable.
 * Treating a green run here as "accessible" is the mistake this comment
 * exists to prevent.
 *
 * Colour contrast is not asserted here: jsdom has no layout or computed
 * colour, so axe's contrast rules cannot run and would report false
 * passes. Contrast is verified against the token ramps in the audit doc.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type {
  Credential,
  InstalledServer,
  IntegrationMetrics,
  McpServer,
  Permission,
  ToolCall,
} from "@/lib/api/integrations";

// ---------------------------------------------------------------------
// jsdom shims for primitives Radix relies on.
// ---------------------------------------------------------------------

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
  // Radix's Select measures its trigger before opening.
  Element.prototype.scrollIntoView ??= function scrollIntoView(): void {};
  globalThis.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof globalThis.matchMedia;
});

// ---------------------------------------------------------------------
// Fixtures — shaped from the generated OpenAPI types, so a backend field
// rename breaks these at type-check rather than silently under-testing.
// ---------------------------------------------------------------------

const CATALOG_ENTRY: McpServer = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "github",
  name: "GitHub",
  description: "Repositories, issues, and pull requests.",
  category: "Developer tools",
  transport: "streamable_http",
  availability: "official",
  auth_scheme: "api_key",
  required_credentials: ["GITHUB_PERSONAL_ACCESS_TOKEN"],
  oauth_scopes: [],
  documentation_url: "https://example.invalid/docs",
  icon_slug: "github",
  is_installable: true,
};

/** The `custom_required` path — an entry that explains why it cannot be installed. */
const UNAVAILABLE_ENTRY: McpServer = {
  ...CATALOG_ENTRY,
  id: "22222222-2222-2222-2222-222222222222",
  slug: "whatsapp",
  name: "WhatsApp",
  description: "Business messaging.",
  category: "Communication",
  availability: "custom_required",
  required_credentials: [],
  documentation_url: null,
  icon_slug: null,
  is_installable: false,
};

const SERVER: InstalledServer = {
  id: "33333333-3333-3333-3333-333333333333",
  workspace_id: "44444444-4444-4444-4444-444444444444",
  mcp_server_id: CATALOG_ENTRY.id,
  display_name: "GitHub",
  transport: "streamable_http",
  endpoint_url: "https://example.invalid/mcp",
  status: "active",
  health: "healthy",
  tools: [
    { name: "list_issues", description: "List issues in a repository.", is_mutating: false },
    { name: "create_issue", description: "Open a new issue.", is_mutating: true },
  ],
  tools_discovered_at: "2026-07-01T00:00:00Z",
  last_health_check_at: "2026-07-01T00:00:00Z",
  last_error: null,
  version: "1.2.0",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

/** The state a user most needs to see, so it must be as accessible as the happy path. */
const SERVER_NEEDING_ATTENTION: InstalledServer = {
  ...SERVER,
  id: "55555555-5555-5555-5555-555555555555",
  display_name: "Internal API",
  mcp_server_id: null,
  status: "pending_auth",
  health: "unreachable",
  last_error: "The server did not respond within 25s.",
};

const CREDENTIAL: Credential = {
  id: "66666666-6666-6666-6666-666666666666",
  installed_server_id: SERVER.id,
  key: "GITHUB_PERSONAL_ACCESS_TOKEN",
  auth_scheme: "api_key",
  hint: "x7f2",
  expires_at: null,
  last_rotated_at: "2026-07-01T00:00:00Z",
  created_at: "2026-07-01T00:00:00Z",
};

const PERMISSION: Permission = {
  id: "77777777-7777-7777-7777-777777777777",
  installed_server_id: SERVER.id,
  agent_id: null,
  team_id: null,
  level: "read_only",
  allowed_tools: [],
  timeout_seconds: 30,
  max_retries: 2,
  cache_ttl_seconds: 0,
  max_calls_per_run: 50,
  priority: 0,
  created_at: "2026-07-01T00:00:00Z",
};

const CALLS: ToolCall[] = [
  {
    id: "88888888-8888-8888-8888-888888888888",
    run_id: null,
    agent_id: null,
    installed_server_id: SERVER.id,
    tool_name: "list_issues",
    status: "success",
    arguments: { repo: "acme/widgets" },
    result_preview: "3 open issues",
    result_bytes: 128,
    duration_ms: 412,
    error_message: null,
    denial_reason: null,
    attempt: 1,
    created_at: "2026-07-01T00:00:00Z",
  },
  {
    id: "99999999-9999-9999-9999-999999999999",
    run_id: null,
    agent_id: null,
    installed_server_id: SERVER.id,
    tool_name: "create_issue",
    status: "denied",
    arguments: { title: "x" },
    result_preview: null,
    result_bytes: null,
    duration_ms: null,
    error_message: null,
    denial_reason: "read_only grant does not permit a mutating tool",
    attempt: 1,
    created_at: "2026-07-01T00:00:00Z",
  },
];

const METRICS: IntegrationMetrics = {
  total_calls: 42,
  succeeded_calls: 39,
  failed_calls: 1,
  denied_calls: 2,
  timed_out_calls: 0,
  cached_calls: 5,
  p95_duration_ms: 880,
  average_duration_ms: 240,
};

const WORKSPACE_ID = SERVER.workspace_id;

// ---------------------------------------------------------------------
// Query-layer stubs. The hooks are replaced, not the network, so these
// tests assert markup rather than re-testing TanStack Query.
// ---------------------------------------------------------------------

const query = <T,>(data: T) => ({
  data,
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
});

const mutation = () => ({ mutate: vi.fn(), isPending: false });

vi.mock("@/lib/queries/integrations", async (importOriginal) => {
  // `needsAttention` is real logic that decides ordering on the
  // connections list — stubbing it would test a layout that never ships.
  const actual = await importOriginal<typeof import("@/lib/queries/integrations")>();
  return {
    ...actual,
    useCatalog: () => query([CATALOG_ENTRY, UNAVAILABLE_ENTRY]),
    useInstalledServers: () => query([SERVER, SERVER_NEEDING_ATTENTION]),
    useInstalledServer: () => query(SERVER),
    useInstallFromCatalog: mutation,
    useRegisterCustomServer: mutation,
    useUninstall: mutation,
    useUpdateInstalled: mutation,
    useCredentials: () => query([CREDENTIAL]),
    usePutCredential: mutation,
    useDeleteCredential: mutation,
    usePermissions: () => query([PERMISSION]),
    useGrantPermission: mutation,
    useRevokePermission: mutation,
    useIntegrationMetrics: () => query(METRICS),
    useToolCalls: () => query({ data: CALLS, next_cursor: null, has_more: false }),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
}));

// Imported after the mocks so the components resolve the stubs.
const { ConnectionsList } = await import("@/components/integrations/connections-list");
const { CredentialsPanel } = await import("@/components/integrations/credentials-panel");
const { Marketplace } = await import("@/components/integrations/marketplace");
const { PermissionsPanel } = await import("@/components/integrations/permissions-panel");
const { RegisterCustomServerDialog } = await import(
  "@/components/integrations/register-custom-server-dialog"
);
const { RuntimeView } = await import("@/components/integrations/runtime-view");
const { ServerDetail } = await import("@/components/integrations/server-detail");

/**
 * Mirrors app/providers.tsx. `TooltipProvider` in particular is not
 * optional scaffolding — the marketplace throws without it, so a wrapper
 * that omitted it would be testing a tree the app never renders.
 */
function Wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
}

/**
 * Runs axe against a rendered container and returns its violations.
 *
 * Contrast rules are disabled because jsdom computes no colour: leaving
 * them on produces a pass that means nothing, which is worse than an
 * acknowledged gap.
 */
async function violationsIn(container: HTMLElement): Promise<axe.Result[]> {
  const results = await axe.run(container, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations;
}

/** Readable failure output — axe's raw objects are unreadable in a diff. */
function describeViolations(violations: axe.Result[]): string {
  return violations
    .map((v) => `${v.id} (${v.impact}): ${v.help}\n    ${v.nodes.map((n) => n.html).join("\n    ")}`)
    .join("\n");
}

afterEach(() => {
  // Explicit because vitest runs without `globals`, so RTL never
  // registers its auto-cleanup. Without this each render stacks onto the
  // previous one's DOM and every `getBy*` finds duplicates.
  cleanup();
  vi.clearAllMocks();
});

describe("Phase 6 integration surfaces — axe", () => {
  it("marketplace has no violations", async () => {
    const { container } = render(
      <Wrapper>
        <Marketplace
          workspaceId={WORKSPACE_ID}
          initialCatalog={[CATALOG_ENTRY, UNAVAILABLE_ENTRY]}
          initialInstalled={[]}
        />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("connections list has no violations, including the attention state", async () => {
    const { container } = render(
      <Wrapper>
        <ConnectionsList
          workspaceId={WORKSPACE_ID}
          initialServers={[SERVER, SERVER_NEEDING_ATTENTION]}
        />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("credentials panel has no violations", async () => {
    const { container } = render(
      <Wrapper>
        <CredentialsPanel workspaceId={WORKSPACE_ID} server={SERVER} />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("permissions panel has no violations", async () => {
    const { container } = render(
      <Wrapper>
        <PermissionsPanel workspaceId={WORKSPACE_ID} server={SERVER} agents={[]} />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("runtime view has no violations, including a denied call", async () => {
    const { container } = render(
      <Wrapper>
        <RuntimeView workspaceId={WORKSPACE_ID} />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("server detail has no violations", async () => {
    const { container } = render(
      <Wrapper>
        <ServerDetail workspaceId={WORKSPACE_ID} initialServer={SERVER} agents={[]} />
      </Wrapper>
    );
    const violations = await violationsIn(container);
    expect(describeViolations(violations)).toBe("");
  });

  it("register-custom-server dialog has no violations once open", async () => {
    render(
      <Wrapper>
        <RegisterCustomServerDialog workspaceId={WORKSPACE_ID} />
      </Wrapper>
    );

    screen.getByRole("button", { name: /add your own/i }).click();

    const dialog = await screen.findByRole("dialog");
    const violations = await violationsIn(dialog);
    expect(describeViolations(violations)).toBe("");
  });
});

/**
 * Structural guarantees axe cannot check, asserted by accessible role and
 * name so they fail when accessibility regresses — not merely when markup
 * changes (accessibility-expert: query by role, never by test-id).
 */
describe("Phase 6 integration surfaces — structural", () => {
  it("names every icon-only control", async () => {
    const { container } = render(
      <Wrapper>
        <CredentialsPanel workspaceId={WORKSPACE_ID} server={SERVER} />
      </Wrapper>
    );

    // The destructive action is the one that must never be a mystery icon.
    expect(
      screen.getByRole("button", { name: `Delete ${CREDENTIAL.key}` })
    ).toBeDefined();

    for (const button of Array.from(container.querySelectorAll("button"))) {
      const name =
        button.getAttribute("aria-label") ??
        button.getAttribute("aria-labelledby") ??
        button.textContent?.trim();
      expect(name, `unnamed button: ${button.outerHTML}`).toBeTruthy();
    }
  });

  it("never conveys tool-call status by colour alone", () => {
    render(
      <Wrapper>
        <RuntimeView workspaceId={WORKSPACE_ID} />
      </Wrapper>
    );

    // A denied call carries the word, not just a warning-toned row —
    // otherwise a colour-blind user cannot tell it from a success.
    const denied = screen.getByText("create_issue").closest("li");
    expect(denied).not.toBeNull();
    expect(within(denied as HTMLElement).getByText(/denied/i)).toBeDefined();
    expect(
      within(denied as HTMLElement).getByText(/read_only grant does not permit/i)
    ).toBeDefined();
  });

  it("states why an unavailable catalog entry cannot be installed", () => {
    render(
      <Wrapper>
        <Marketplace
          workspaceId={WORKSPACE_ID}
          initialCatalog={[CATALOG_ENTRY, UNAVAILABLE_ENTRY]}
          initialInstalled={[]}
        />
      </Wrapper>
    );

    // A disabled button is skipped by a screen reader's button list, so
    // the reason has to be readable text on the card — not conveyed only
    // by the `disabled` attribute.
    const heading = screen.getByRole("heading", { name: UNAVAILABLE_ENTRY.name });
    const card = heading.closest("[data-slot='card']");
    expect(card).not.toBeNull();

    const button = within(card as HTMLElement).getByRole("button", { name: /unavailable/i });
    expect(button).toHaveProperty("disabled", true);

    // The card carries the availability summary in prose.
    expect((card as HTMLElement).textContent).toMatch(/no .{0,40}server/i);
  });
});
