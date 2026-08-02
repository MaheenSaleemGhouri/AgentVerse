import type { Metadata } from "next";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";
import { ApiError } from "@/lib/api/client";
import { acceptInvite, type AcceptInviteResponse } from "@/lib/api/invitations";

import { AgentVerseLockup } from "@/components/auth/agentverse-mark";
import { GlassPanel } from "@/components/auth/glass-panel";

export const metadata: Metadata = {
  title: "Accept invitation — AgentVerse",
};

const FALLBACK_INVALID_MESSAGE = "This invite link has expired, was already used, or is invalid.";

/** `ApiError.message` is the raw response body — FastAPI's error shape
 * is `{"detail": "..."}`, not free text — so this unwraps it rather
 * than showing raw JSON to the user. */
function extractDetail(rawBody: string): string {
  try {
    const parsed: unknown = JSON.parse(rawBody);
    if (
      parsed &&
      typeof parsed === "object" &&
      "detail" in parsed &&
      typeof parsed.detail === "string"
    ) {
      return parsed.detail;
    }
  } catch {
    // Not JSON — fall through to the generic message below.
  }
  return FALLBACK_INVALID_MESSAGE;
}

function InvalidInviteCard({ message }: { message: string }): React.JSX.Element {
  return (
    <div className="mx-auto flex w-full max-w-[520px] flex-col px-4 py-16 sm:px-6">
      <GlassPanel>
        <AgentVerseLockup className="mb-6" />
        <h1 className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight text-white">
          <AlertTriangle className="size-5 text-[#c084fc]" aria-hidden="true" />
          Invitation not valid
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[#a8a2c8]">{message}</p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex items-center gap-2 rounded-lg px-1 text-sm font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
        >
          Go to AgentVerse
        </Link>
      </GlassPanel>
    </div>
  );
}

export default async function AcceptInvitePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}): Promise<React.JSX.Element> {
  const { token } = await searchParams;

  if (!token) {
    return <InvalidInviteCard message="This invite link is missing its token." />;
  }

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    // The caller isn't a member of the target yet, but they still need
    // an AgentVerse account to accept — send them to log in (or sign up)
    // and back here with the token intact.
    redirect(`/login?redirect=${encodeURIComponent(`/invite/accept?token=${token}`)}`);
  }

  let result: AcceptInviteResponse;
  try {
    result = await acceptInvite(token);
  } catch (error) {
    // `redirect()` below must never run inside this catch (it throws its
    // own control-flow error) — the try block covers only the API call.
    if (error instanceof ApiError) {
      return <InvalidInviteCard message={extractDetail(error.message)} />;
    }
    throw error;
  }

  redirect(
    result.target_type === "workspace"
      ? `/dashboard/${result.target_id}`
      : `/organizations/${result.target_id}/members`
  );
}
