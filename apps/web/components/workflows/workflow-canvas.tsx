"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import * as React from "react";

import type { Agent } from "@/lib/api/agents";
import type { Team } from "@/lib/api/teams";
import type { WorkflowEdge, WorkflowNode, WorkflowNodeType } from "@/lib/api/workflows";
import type { CollabEvent, CollabEventInput } from "@/lib/hooks/useWorkflowCollab";
import { useWorkflowBuilderStore } from "@/lib/stores/workflow-builder-store";
import { WORKFLOW_NODE_META } from "@/lib/workflows/node-types";
import { cn } from "@/lib/utils";

import { NodeConfigPanel } from "@/components/workflows/node-config-panel";
import { NodePalette } from "@/components/workflows/node-palette";

type CanvasNodeData = {
  nodeType: WorkflowNodeType;
  config: Record<string, unknown>;
  agentId: string | null;
  teamId: string | null;
};
type CanvasNode = Node<CanvasNodeData, "workflowNode">;
type CanvasEdgeData = { condition: WorkflowEdge["condition"]; branchOrder: number | null };
type CanvasEdge = Edge<CanvasEdgeData>;

function toCanvasNode(node: WorkflowNode): CanvasNode {
  return {
    id: node.id,
    type: "workflowNode",
    position: { x: node.position_x, y: node.position_y },
    data: {
      nodeType: node.type,
      config: node.config ?? {},
      agentId: node.agent_id ?? null,
      teamId: node.team_id ?? null,
    },
  };
}

function toWorkflowNode(node: CanvasNode): WorkflowNode {
  return {
    id: node.id,
    type: node.data.nodeType,
    position_x: node.position.x,
    position_y: node.position.y,
    config: node.data.config,
    agent_id: node.data.agentId,
    team_id: node.data.teamId,
  };
}

function toCanvasEdge(edge: WorkflowEdge): CanvasEdge {
  return {
    id: edge.id,
    source: edge.from_node_id,
    target: edge.to_node_id,
    data: { condition: edge.condition ?? null, branchOrder: edge.branch_order ?? null },
    label: conditionLabel(edge.condition ?? null),
  };
}

function toWorkflowEdge(edge: CanvasEdge): WorkflowEdge {
  return {
    id: edge.id,
    from_node_id: edge.source,
    to_node_id: edge.target,
    condition: edge.data?.condition ?? null,
    branch_order: edge.data?.branchOrder ?? null,
  };
}

function conditionLabel(condition: WorkflowEdge["condition"]): string | undefined {
  if (!condition) return undefined;
  const field = condition.field as string | undefined;
  const operator = condition.operator as string | undefined;
  const value = condition.value as string | undefined;
  if (!field) return "condition";
  return `${field} ${operator ?? "equals"} ${value ?? ""}`.trim();
}

function WorkflowNodeCard({ id, data, selected }: NodeProps<CanvasNode>): React.JSX.Element {
  const meta = WORKFLOW_NODE_META[data.nodeType];
  const Icon = meta.icon;
  const isUnconfigured =
    (data.nodeType === "agent_step" && !data.agentId) ||
    (data.nodeType === "team_step" && !data.teamId);

  return (
    <div
      className={cn(
        "min-w-44 rounded-xl border bg-card px-3 py-2.5 shadow-sm transition-colors",
        selected ? "border-primary ring-2 ring-primary/20" : "border-border"
      )}
      data-node-id={id}
    >
      <Handle type="target" position={Position.Top} className="!bg-primary" />
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground"
        >
          <Icon className="size-3.5" />
        </span>
        <span className="truncate text-sm font-medium">{meta.label}</span>
      </div>
      {isUnconfigured && (
        <p className="mt-1 text-xs text-warning">
          {data.nodeType === "agent_step" ? "No agent chosen" : "No team chosen"}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  );
}

const NODE_TYPES: NodeTypes = { workflowNode: WorkflowNodeCard };

function nextPosition(existing: CanvasNode[]): { x: number; y: number } {
  const count = existing.length;
  return { x: 80 + (count % 4) * 220, y: 80 + Math.floor(count / 4) * 140 };
}

export function WorkflowCanvas({
  initialNodes,
  initialEdges,
  agents,
  teams,
  onGraphChange,
  remoteEvent,
  onLocalEvent,
}: {
  initialNodes: WorkflowNode[];
  initialEdges: WorkflowEdge[];
  agents: Agent[];
  teams: Team[];
  onGraphChange: (nodes: WorkflowNode[], edges: WorkflowEdge[]) => void;
  remoteEvent: CollabEvent | null;
  onLocalEvent: (event: CollabEventInput) => void;
}): React.JSX.Element {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner
        initialNodes={initialNodes}
        initialEdges={initialEdges}
        agents={agents}
        teams={teams}
        onGraphChange={onGraphChange}
        remoteEvent={remoteEvent}
        onLocalEvent={onLocalEvent}
      />
    </ReactFlowProvider>
  );
}

function WorkflowCanvasInner({
  initialNodes,
  initialEdges,
  agents,
  teams,
  onGraphChange,
  remoteEvent,
  onLocalEvent,
}: {
  initialNodes: WorkflowNode[];
  initialEdges: WorkflowEdge[];
  agents: Agent[];
  teams: Team[];
  onGraphChange: (nodes: WorkflowNode[], edges: WorkflowEdge[]) => void;
  remoteEvent: CollabEvent | null;
  onLocalEvent: (event: CollabEventInput) => void;
}): React.JSX.Element {
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
    initialNodes.map(toCanvasNode)
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<CanvasEdge>(
    initialEdges.map(toCanvasEdge)
  );
  const selectedNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const selectedEdgeId = useWorkflowBuilderStore((s) => s.selectedEdgeId);
  const selectNode = useWorkflowBuilderStore((s) => s.selectNode);
  const selectEdge = useWorkflowBuilderStore((s) => s.selectEdge);
  const setDirty = useWorkflowBuilderStore((s) => s.setDirty);

  // The parent (WorkflowBuilder) owns the "current draft" it will send
  // to Save — this canvas is the only place that actually mutates the
  // graph, so every change is reported up rather than duplicated state.
  React.useEffect(() => {
    onGraphChange(nodes.map(toWorkflowNode), edges.map(toWorkflowEdge));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onGraphChange is a fresh closure every render in the parent; only nodes/edges identity should trigger this
  }, [nodes, edges]);

  // Applies a collaborator's live edit — last-write-wins per node
  // position/edge, the documented conflict rule (docs/adr/0016). The
  // Redis relay echoes every publish back to its own sender too, so
  // every branch here is written idempotently (id-existence checks
  // before insert, plain filters for remove) rather than trying to
  // suppress the sender's own echo — simpler, and correct either way.
  React.useEffect(() => {
    if (!remoteEvent) return;
    if (remoteEvent.type === "node_moved") {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === remoteEvent.node_id ? { ...n, position: { x: remoteEvent.x, y: remoteEvent.y } } : n
        )
      );
    } else if (remoteEvent.type === "node_added") {
      setNodes((nds) =>
        nds.some((n) => n.id === remoteEvent.node_id)
          ? nds
          : [
              ...nds,
              {
                id: remoteEvent.node_id,
                type: "workflowNode",
                position: { x: remoteEvent.x, y: remoteEvent.y },
                data: {
                  nodeType: remoteEvent.node_type as WorkflowNodeType,
                  config: {},
                  agentId: null,
                  teamId: null,
                },
              },
            ]
      );
    } else if (remoteEvent.type === "node_removed") {
      setNodes((nds) => nds.filter((n) => n.id !== remoteEvent.node_id));
      setEdges((eds) => eds.filter((e) => e.source !== remoteEvent.node_id && e.target !== remoteEvent.node_id));
    } else if (remoteEvent.type === "edge_added") {
      setEdges((eds) =>
        eds.some((e) => e.id === remoteEvent.edge_id)
          ? eds
          : [
              ...eds,
              {
                id: remoteEvent.edge_id,
                source: remoteEvent.from_node_id,
                target: remoteEvent.to_node_id,
                data: { condition: null, branchOrder: null },
              },
            ]
      );
    } else if (remoteEvent.type === "edge_removed") {
      setEdges((eds) => eds.filter((e) => e.id !== remoteEvent.edge_id));
    }
  }, [remoteEvent, setNodes, setEdges]);

  function markDirty(): void {
    setDirty(true);
  }

  function handleAddNode(type: WorkflowNodeType): void {
    const id = crypto.randomUUID();
    const position = nextPosition(nodes);
    setNodes((nds) => [
      ...nds,
      {
        id,
        type: "workflowNode",
        position,
        data: { nodeType: type, config: {}, agentId: null, teamId: null },
      },
    ]);
    markDirty();
    onLocalEvent({ type: "node_added", node_id: id, node_type: type, x: position.x, y: position.y });
    selectNode(id);
  }

  function handleConnect(connection: Connection): void {
    if (!connection.source || !connection.target || connection.source === connection.target) {
      return;
    }
    const id = crypto.randomUUID();
    const source = connection.source;
    const target = connection.target;
    setEdges((eds) => [
      ...eds,
      {
        id,
        source,
        target,
        data: { condition: null, branchOrder: null },
      },
    ]);
    onLocalEvent({ type: "edge_added", edge_id: id, from_node_id: source, to_node_id: target });
    markDirty();
  }

  function handleNodeDragStop(_event: unknown, node: CanvasNode): void {
    markDirty();
    onLocalEvent({ type: "node_moved", node_id: node.id, x: node.position.x, y: node.position.y });
  }

  function updateNode(nodeId: string, patch: Partial<WorkflowNode>): void {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === nodeId
          ? {
              ...n,
              data: {
                nodeType: patch.type ?? n.data.nodeType,
                config: patch.config ?? n.data.config,
                agentId: patch.agent_id !== undefined ? patch.agent_id : n.data.agentId,
                teamId: patch.team_id !== undefined ? patch.team_id : n.data.teamId,
              },
            }
          : n
      )
    );
    markDirty();
  }

  function updateEdge(edgeId: string, patch: Partial<WorkflowEdge>): void {
    setEdges((eds) =>
      eds.map((e) =>
        e.id === edgeId
          ? {
              ...e,
              data: {
                condition: patch.condition !== undefined ? patch.condition : (e.data?.condition ?? null),
                branchOrder:
                  patch.branch_order !== undefined ? patch.branch_order : (e.data?.branchOrder ?? null),
              },
              label: conditionLabel(
                patch.condition !== undefined ? patch.condition : (e.data?.condition ?? null)
              ),
            }
          : e
      )
    );
    markDirty();
  }

  function deleteNode(nodeId: string): void {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    selectNode(null);
    markDirty();
    onLocalEvent({ type: "node_removed", node_id: nodeId });
  }

  function deleteEdge(edgeId: string): void {
    setEdges((eds) => eds.filter((e) => e.id !== edgeId));
    selectEdge(null);
    markDirty();
    onLocalEvent({ type: "edge_removed", edge_id: edgeId });
  }

  const selectedNode = React.useMemo(
    () => (selectedNodeId ? (nodes.find((n) => n.id === selectedNodeId) ?? null) : null),
    [nodes, selectedNodeId]
  );
  const selectedEdgeContext = React.useMemo(() => {
    if (!selectedEdgeId) return null;
    const edge = edges.find((e) => e.id === selectedEdgeId);
    if (!edge) return null;
    const sourceNode = nodes.find((n) => n.id === edge.source);
    if (!sourceNode) return null;
    return { edge: toWorkflowEdge(edge), sourceNodeType: sourceNode.data.nodeType };
  }, [edges, nodes, selectedEdgeId]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_320px]">
      <div className="relative h-[520px] overflow-hidden rounded-xl border border-border bg-secondary/30">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onNodeDragStop={handleNodeDragStop}
          onNodeClick={(_event, node) => selectNode(node.id)}
          onEdgeClick={(_event, edge) => selectEdge(edge.id)}
          onPaneClick={() => {
            selectNode(null);
            selectEdge(null);
          }}
          onNodesDelete={(deleted) => deleted.forEach((n) => deleteNode(n.id))}
          onEdgesDelete={(deleted) => deleted.forEach((e) => deleteEdge(e.id))}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable className="!bg-card" />
          <Panel position="top-left">
            <NodePalette onAdd={handleAddNode} />
          </Panel>
        </ReactFlow>
      </div>

      <NodeConfigPanel
        selectedNode={selectedNode ? toWorkflowNode(selectedNode) : null}
        selectedEdge={selectedEdgeContext}
        agents={agents}
        teams={teams}
        onUpdateNode={updateNode}
        onUpdateEdge={updateEdge}
        onDeleteNode={deleteNode}
        onDeleteEdge={deleteEdge}
      />
    </div>
  );
}
