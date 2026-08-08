import { notFound } from "next/navigation";
import * as React from "react";

import { isPlatformAdmin, listModerationQueue } from "@/lib/api/admin";

import { ModerationQueue } from "@/components/admin/moderation-queue";
import { PageHeader } from "@/components/patterns/page-header";

/**
 * Marketplace moderation — platform staff only.
 *
 * Lives under the workspace shell so staff keep the navigation and
 * switcher they already have, but it is *not* a workspace-scoped
 * capability: the queue spans every workspace's submissions, and the
 * `workspaceId` in the URL is chrome, never authority. Authority is
 * `platform_admins`, checked by the API on every call below.
 *
 * `notFound()` rather than a "you do not have access" page, matching
 * `require_platform_admin`'s own 404: a moderation surface should not
 * confirm its existence to someone who has no business there.
 */
export default async function MarketplaceModerationPage(): Promise<React.JSX.Element> {
  if (!(await isPlatformAdmin())) {
    notFound();
  }

  const queue = await listModerationQueue();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Marketplace moderation"
        description="Listings submitted for review, oldest first. Approving one publishes it to every workspace's catalog."
      />
      <ModerationQueue initialQueue={queue} />
    </div>
  );
}

export const metadata = {
  title: "Marketplace moderation · AgentVerse",
};
