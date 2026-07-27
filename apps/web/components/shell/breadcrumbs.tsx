"use client";

import Link from "next/link";
import { useSelectedLayoutSegments } from "next/navigation";
import * as React from "react";

import { NAV_SECTIONS } from "@/lib/navigation";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

/**
 * Derived from the route, never hand-passed per page — a page that
 * forgets to declare its own trail is the usual way breadcrumbs go
 * stale.
 *
 * Segment labels resolve through the shared nav model where one exists;
 * an opaque id segment (an agent or KB uuid) is rendered as a short
 * monospace token rather than a raw 36-character uuid, which would
 * dominate the bar and tell the user nothing.
 */
export function Breadcrumbs({ workspaceId }: { workspaceId: string }): React.JSX.Element | null {
  const segments = useSelectedLayoutSegments();

  if (segments.length === 0) return null;

  const crumbs = segments.map((segment, index) => {
    const path = segments.slice(0, index + 1).join("/");
    const match = NAV_SECTIONS.find((item) => item.segment === path || item.segment === segment);
    const isId = /^[0-9a-f]{8}-[0-9a-f]{4}/i.test(segment);

    return {
      key: path,
      href: `/dashboard/${workspaceId}/${path}`,
      label: match?.label ?? (isId ? segment.slice(0, 8) : toTitleCase(segment)),
      isMono: isId && !match,
    };
  });

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink asChild>
            <Link href={`/dashboard/${workspaceId}`}>Workspace</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        {crumbs.map((crumb, index) => (
          <React.Fragment key={crumb.key}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              {index === crumbs.length - 1 ? (
                <BreadcrumbPage className={crumb.isMono ? "font-mono text-xs" : undefined}>
                  {crumb.label}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link href={crumb.href} className={crumb.isMono ? "font-mono text-xs" : undefined}>
                    {crumb.label}
                  </Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

function toTitleCase(segment: string): string {
  return segment
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
