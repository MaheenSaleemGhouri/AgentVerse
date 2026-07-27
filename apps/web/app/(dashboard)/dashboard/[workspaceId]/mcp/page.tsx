import { Globe, Plug, ShieldCheck, Terminal } from "lucide-react";

import { IntegrationPending } from "@/components/patterns/integration-pending";
import { PageHeader } from "@/components/patterns/page-header";
import { Card } from "@/components/ui/card";

const TRANSPORTS = [
  {
    icon: Terminal,
    label: "stdio",
    description:
      "For co-located servers you control. The process runs alongside the worker with no network hop.",
  },
  {
    icon: Globe,
    label: "SSE / streamable HTTP",
    description:
      "For remote and third-party servers, reached through the egress control point rather than a direct socket.",
  },
];

const GUARANTEES = [
  "Connections are workspace-scoped and credential-isolated — secrets resolve at call time and are never stored in agent config or logged.",
  "Tool schemas are validated end to end, and arguments returned by a model are checked before anything executes.",
  "Tool results are treated as untrusted external content and sanitised before re-entering agent context.",
  "An unreachable server disables only its own tools for that run, with a trace event — it never crashes the run.",
];

export default function McpPage(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="MCP"
        description="Connect Model Context Protocol servers and give your agents their tools."
      />

      <IntegrationPending feature="mcp">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">Supported transports</h2>
            <div className="space-y-3">
              {TRANSPORTS.map((transport) => {
                const Icon = transport.icon;
                return (
                  <Card key={transport.label} className="gap-2 p-5">
                    <div className="flex items-center gap-2.5">
                      <span
                        aria-hidden="true"
                        className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground"
                      >
                        <Icon className="size-4" />
                      </span>
                      <p className="font-mono text-sm font-medium">{transport.label}</p>
                    </div>
                    <p className="text-sm text-muted-foreground">{transport.description}</p>
                  </Card>
                );
              })}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">How tools will be handled</h2>
            <Card className="gap-3 p-5">
              <span
                aria-hidden="true"
                className="flex size-8 items-center justify-center rounded-lg bg-success-soft text-success"
              >
                <ShieldCheck className="size-4" />
              </span>
              <ul className="space-y-2.5">
                {GUARANTEES.map((guarantee) => (
                  <li key={guarantee} className="flex gap-2 text-sm text-muted-foreground">
                    <Plug
                      className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/60"
                      aria-hidden="true"
                    />
                    {guarantee}
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        </div>
      </IntegrationPending>
    </div>
  );
}

export const metadata = {
  title: "MCP · AgentVerse",
};
