import { create } from "zustand";

export type BuilderPanelTab = "instructions" | "model" | "tools" | "knowledge";

interface AgentBuilderState {
  activeTab: BuilderPanelTab;
  isDirty: boolean;
  setActiveTab: (tab: BuilderPanelTab) => void;
  setDirty: (dirty: boolean) => void;
  reset: () => void;
}

const initialState = { activeTab: "instructions" as BuilderPanelTab, isDirty: false };

/**
 * Ephemeral UI state for a single builder session — never the agent's
 * config itself, which is server-originated data owned by react-hook-form
 * + the mutation layer (CLAUDE.md §6: server state and client/UI state
 * are never mixed in the same store). The consuming page calls `reset()`
 * on unmount so state never leaks into the next agent's builder session.
 */
export const useAgentBuilderStore = create<AgentBuilderState>((set) => ({
  ...initialState,
  setActiveTab: (tab) => set({ activeTab: tab }),
  setDirty: (dirty) => set({ isDirty: dirty }),
  reset: () => set(initialState),
}));
