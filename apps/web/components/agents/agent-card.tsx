"use client";

import { Bot, MoreVertical, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { deleteAgentAction } from "@/lib/api/actions";
import type { Agent } from "@/lib/api/agents";

import { AgentStatusBadge } from "@/components/agents/agent-status-badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function AgentCard({
  workspaceId,
  agent,
}: {
  workspaceId: string;
  agent: Agent;
}): React.JSX.Element {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete(): Promise<void> {
    setIsDeleting(true);
    try {
      await deleteAgentAction(workspaceId, agent.id);
      toast.success(`"${agent.name}" deleted`);
      router.refresh();
    } catch {
      toast.error("Could not delete the agent — try again.");
      setIsDeleting(false);
    }
  }

  return (
    <Card className="transition-colors hover:border-primary/40">
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
            <Bot className="size-4" />
          </span>
          <CardTitle>
            <Link href={`/dashboard/${workspaceId}/agents/${agent.id}/builder`}>{agent.name}</Link>
          </CardTitle>
        </div>
        <CardDescription>{agent.description ?? "No description"}</CardDescription>
        <CardAction>
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              aria-label={`Actions for ${agent.name}`}
            >
              <MoreVertical className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                variant="destructive"
                disabled={isDeleting}
                onSelect={(event) => {
                  event.preventDefault();
                  void handleDelete();
                }}
              >
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>
      <CardContent>
        <AgentStatusBadge status={agent.status} />
      </CardContent>
    </Card>
  );
}
