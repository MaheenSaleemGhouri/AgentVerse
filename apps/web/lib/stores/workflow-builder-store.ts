import { create } from "zustand";

interface WorkflowBuilderState {
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  isDirty: boolean;
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;
  setDirty: (dirty: boolean) => void;
  reset: () => void;
}

const initialState = { selectedNodeId: null, selectedEdgeId: null, isDirty: false };

/**
 * Ephemeral, session-scoped canvas UI state only — never the workflow
 * graph itself (nodes/edges/config), which is server-originated data
 * owned by the TanStack Query cache and saved as an immutable
 * `workflow_version` (CLAUDE.md §6, mirroring `useAgentBuilderStore`).
 * The consuming page calls `reset()` on unmount so a stale selection
 * never leaks into the next workflow's builder session.
 *
 * Node and edge selection are mutually exclusive — selecting one clears
 * the other — because the inspector panel renders either a node's
 * config form or an edge's condition form, never both at once.
 */
export const useWorkflowBuilderStore = create<WorkflowBuilderState>((set) => ({
  ...initialState,
  selectNode: (nodeId) => set({ selectedNodeId: nodeId, selectedEdgeId: null }),
  selectEdge: (edgeId) => set({ selectedEdgeId: edgeId, selectedNodeId: null }),
  setDirty: (dirty) => set({ isDirty: dirty }),
  reset: () => set(initialState),
}));
