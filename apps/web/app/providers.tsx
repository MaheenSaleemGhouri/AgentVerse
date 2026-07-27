"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * The one client-side composition root for cross-cutting providers
 * (CLAUDE.md §6: React Context/providers reserved for cross-cutting,
 * rarely-changing values — theme and the TanStack Query client are
 * exactly that; server state itself is never held here).
 *
 * `useState(() => new QueryClient())` — not a module-level singleton —
 * so each request gets its own client on the server, avoiding cache
 * leakage between users; the client only ever constructs one instance
 * per mount in the browser.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Server-originated data gets an explicit staleTime rather
            // than the default 0 (CLAUDE.md §6) — without it every
            // remount refetches, which on a dashboard of several panels
            // is a burst of redundant requests. Per-hook staleTime
            // overrides this where the data is more volatile.
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          {children}
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
