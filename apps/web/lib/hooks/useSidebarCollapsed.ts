"use client";

import * as React from "react";

const STORAGE_KEY = "agentverse.sidebar.collapsed";

/**
 * Whether the desktop sidebar is collapsed to its icon rail.
 *
 * Read from `localStorage` in an effect rather than during render, so
 * the server and the first client render agree. Reading storage during
 * render is the classic hydration mismatch: the server has no idea what
 * the user chose, and React discards the whole tree when they disagree.
 *
 * The one-frame flash that costs is contained by rendering the sidebar
 * at its expanded width first — a rail that widens is a smaller visual
 * error than content that jumps left.
 */
export function useSidebarCollapsed(): {
  collapsed: boolean;
  toggle: () => void;
  /** False until the stored preference has been read, so the toggle can
   * avoid animating into its restored position on first paint. */
  ready: boolean;
} {
  const [collapsed, setCollapsed] = React.useState(false);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(STORAGE_KEY) === "true");
    } catch {
      // Storage can throw in private modes and sandboxed frames. The
      // default is a working sidebar, so there is nothing to recover.
    }
    setReady(true);
  }, []);

  const toggle = React.useCallback(() => {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // Preference simply does not persist; the toggle still works.
      }
      return next;
    });
  }, []);

  return { collapsed, toggle, ready };
}
