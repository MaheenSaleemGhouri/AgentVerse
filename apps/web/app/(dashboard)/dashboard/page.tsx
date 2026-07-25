import { redirect } from "next/navigation";

import { listMyWorkspaces } from "@/lib/api/workspaces";

import { CreateWorkspaceForm } from "./create-workspace-form";

export default async function DashboardIndexPage(): Promise<React.JSX.Element> {
  const workspaces = await listMyWorkspaces();

  if (workspaces.length === 0) {
    return <CreateWorkspaceForm />;
  }

  redirect(`/dashboard/${workspaces[0]!.id}`);
}
