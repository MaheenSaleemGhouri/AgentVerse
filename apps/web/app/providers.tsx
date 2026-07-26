"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";

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
  const [queryClient] = useState(() => new QueryClient());

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
