import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { formatDateTime, initialsFrom } from "@/lib/format";

import { CopyButton } from "@/components/patterns/copy-button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/**
 * Read-only by design.
 *
 * The auth provider owns identity — name, email, and password all change
 * through it, not through a workspace-scoped API. Rendering editable
 * fields that had nowhere to submit to would be worse than showing the
 * truth.
 */
export default async function ProfilePage(): Promise<React.JSX.Element> {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");

  const { user } = session;

  return (
    <div className="max-w-2xl space-y-6">
      <Card className="gap-4 p-6">
        <div className="flex items-center gap-4">
          <Avatar className="size-14">
            <AvatarFallback className="text-base">
              {initialsFrom(user.name || user.email)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <h2 className="font-medium">{user.name || "Unnamed"}</h2>
            <p className="truncate text-sm text-muted-foreground">{user.email}</p>
          </div>
        </div>
        <Separator />
        <Row label="Name" value={user.name || "Not set"} />
        <Row label="Email" value={user.email} />
        <Row label="Email verified" value={user.emailVerified ? "Yes" : "No"} />
        <Row label="User ID" value={user.id} mono copyable />
        <Row label="Joined" value={formatDateTime(String(user.createdAt))} />
      </Card>

      <Card className="gap-2 p-6">
        <h2 className="font-medium">Sharing your user ID</h2>
        <p className="text-sm text-muted-foreground">
          A workspace admin needs your user ID to add you to their workspace. It identifies you but
          grants nothing on its own — it is safe to share.
        </p>
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  copyable,
}: {
  label: string;
  value: string;
  mono?: boolean;
  copyable?: boolean;
}): React.JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-sm text-muted-foreground">{label}</span>
      <span
        className={mono ? "min-w-0 flex-1 truncate font-mono text-sm" : "min-w-0 flex-1 text-sm"}
      >
        {value}
      </span>
      {copyable && <CopyButton value={value} label={`Copy ${label}`} size="icon-xs" />}
    </div>
  );
}

export const metadata = {
  title: "Profile · AgentVerse",
};
