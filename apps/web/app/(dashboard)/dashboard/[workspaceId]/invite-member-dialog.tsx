"use client";

import { useRef, useState } from "react";

import { inviteMember, type Role } from "@/lib/api/workspaces";

import { ALL_ROLES } from "./role-order";

/**
 * Native <dialog> — focus is trapped and returned to the trigger
 * automatically by the browser (CLAUDE.md §15's "focus is trapped and
 * restored for every modal" requirement, satisfied without a UI
 * library since shadcn/ui isn't introduced until Phase 4).
 */
export function InviteMemberDialog({
  workspaceId,
  onInvited,
}: {
  workspaceId: string;
  onInvited: () => void;
}): React.JSX.Element {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function open(): void {
    setError(null);
    dialogRef.current?.showModal();
  }

  function close(): void {
    dialogRef.current?.close();
    setUserId("");
    setRole("member");
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await inviteMember(workspaceId, userId, role);
      close();
      onInvited();
    } catch {
      setError("Could not invite this member. Check the user id and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
      >
        Invite member
      </button>

      <dialog
        ref={dialogRef}
        onCancel={close}
        aria-labelledby="invite-dialog-title"
        className="w-full max-w-sm rounded-lg border border-neutral-200 p-6 backdrop:bg-black/40 dark:border-neutral-700 dark:bg-neutral-900"
      >
        <h2 id="invite-dialog-title" className="mb-4 text-lg font-semibold">
          Invite a teammate
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="invite-user-id" className="text-sm font-medium">
              User ID
            </label>
            <input
              id="invite-user-id"
              type="text"
              required
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              className="rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-neutral-700 dark:bg-neutral-950"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="invite-role" className="text-sm font-medium">
              Role
            </label>
            <select
              id="invite-role"
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950"
            >
              {ALL_ROLES.filter((r) => r !== "owner").map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={close}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || userId.trim().length === 0}
              className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {isSubmitting ? "Inviting…" : "Invite"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
