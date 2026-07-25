"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createWorkspace } from "@/lib/api/workspaces";

export function CreateWorkspaceForm(): React.JSX.Element {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const workspace = await createWorkspace(name);
      router.push(`/dashboard/${workspace.id}`);
      router.refresh();
    } catch {
      setError("Could not create the workspace. Try a different name.");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 pt-16">
      <h1 className="text-xl font-semibold">Create your first workspace</h1>
      <p className="text-sm text-neutral-500">
        A workspace is where your agents, knowledge bases, and teammates live.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        <label htmlFor="workspace-name" className="text-sm font-medium">
          Workspace name
        </label>
        <input
          id="workspace-name"
          name="name"
          type="text"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Inc."
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={isSubmitting || name.trim().length === 0}
          className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create workspace"}
        </button>
      </form>
    </div>
  );
}
