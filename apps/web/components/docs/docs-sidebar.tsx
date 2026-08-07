"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { cn } from "@/lib/utils";

export interface SidebarSection {
  readonly slug: string;
  readonly name: string;
  readonly guides: readonly { readonly slug: string; readonly title: string }[];
}

/**
 * Pillar navigation.
 *
 * A client component only because it highlights the current page, which
 * needs `usePathname`. The sections themselves are computed on the
 * server from the guide corpus and passed down, so no content ships as
 * a second copy.
 */
export function DocsSidebar({
  sections,
}: {
  sections: readonly SidebarSection[];
}): React.JSX.Element {
  const pathname = usePathname();

  return (
    <nav aria-label="Documentation" className="space-y-6">
      {sections.map((section) => (
        <div key={section.slug}>
          <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {section.name}
          </h2>
          <ul className="space-y-0.5">
            {section.guides.map((guide) => {
              const href = `/docs/${guide.slug}`;
              const active = pathname === href;
              return (
                <li key={guide.slug}>
                  <Link
                    href={href}
                    // `aria-current` rather than colour alone: a screen
                    // reader gets the same "you are here" the sighted
                    // reader gets from the highlight.
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block rounded-md px-2 py-1.5 text-sm transition-colors",
                      active
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                  >
                    {guide.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
