"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { changeMemberRoleAction, removeMemberAction } from "@/lib/api/actions";
import type { Member, Role } from "@/lib/api/workspaces";

import { InviteMemberDialog } from "./invite-member-dialog";
import { ALL_ROLES, roleSatisfies } from "./role-order";

export function MembersPanel({
  workspaceId,
  members,
  viewerRole,
}: {
  workspaceId: string;
  members: Member[];
  viewerRole: Role;
}): React.JSX.Element {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  const canInvite = roleSatisfies(viewerRole, "admin");
  const canManage = roleSatisfies(viewerRole, "owner");

  function refresh(): void {
    router.refresh();
  }

  async function handleRoleChange(userId: string, role: Role): Promise<void> {
    setError(null);
    try {
      await changeMemberRoleAction(workspaceId, userId, role);
      refresh();
    } catch {
      setError("Could not change this member's role.");
    }
  }

  async function handleRemove(userId: string): Promise<void> {
    setError(null);
    try {
      await removeMemberAction(workspaceId, userId);
      refresh();
    } catch {
      setError("Could not remove this member — a workspace must always have an owner.");
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-500">Members</h2>
        {canInvite && <InviteMemberDialog workspaceId={workspaceId} onInvited={refresh} />}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <ul className="flex flex-col divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
        {members.map((member) => (
          <li key={member.user_id} className="flex items-center justify-between gap-4 px-4 py-3">
            <span className="text-sm">{member.user_id}</span>
            <div className="flex items-center gap-3">
              {canManage ? (
                <label>
                  <span className="sr-only">Role for {member.user_id}</span>
                  <select
                    value={member.role}
                    onChange={(event) =>
                      handleRoleChange(member.user_id, event.target.value as Role)
                    }
                    className="rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                  >
                    {ALL_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <span className="text-sm text-neutral-500">{member.role}</span>
              )}
              {canManage && (
                <button
                  type="button"
                  onClick={() => handleRemove(member.user_id)}
                  className="text-sm text-red-600 hover:underline dark:text-red-400"
                >
                  Remove
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
