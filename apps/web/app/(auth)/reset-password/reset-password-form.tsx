"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AgentVerseLockup } from "@/components/auth/agentverse-mark";
import { AuthField } from "@/components/auth/auth-field";
import { GradientButton } from "@/components/auth/auth-buttons";
import { GlassPanel } from "@/components/auth/glass-panel";
import { authClient } from "@/lib/auth-client";

const schema = z.object({
  password: z.string().min(8, "At least 8 characters.").max(128),
});
type FormValues = z.infer<typeof schema>;

/**
 * Landed on from the link Better Auth redirects to after validating the
 * emailed token server-side (`requestPasswordResetCallback`) — the token
 * arrives as `?token=` on success, or `?error=INVALID_TOKEN` if the link
 * was already used or has expired.
 */
export function ResetPasswordForm(): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const linkError = searchParams.get("error");
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { password: "" } });

  async function onSubmit(values: FormValues): Promise<void> {
    if (!token) return;
    setFormError(null);
    const { error } = await authClient.resetPassword({ newPassword: values.password, token });
    if (error) {
      setFormError(error.message ?? "Could not reset the password. Request a new link.");
      return;
    }
    router.push("/login");
  }

  if (!token || linkError) {
    return (
      <div className="mx-auto flex w-full max-w-[520px] flex-col px-4 py-16 sm:px-6">
        <GlassPanel>
          <AgentVerseLockup className="mb-6" />
          <h1 className="text-2xl font-semibold tracking-tight text-white">Link expired</h1>
          <p className="mt-2 text-sm leading-relaxed text-[#a8a2c8]">
            This reset link is invalid or has already been used. Request a new one.
          </p>
          <Link
            href="/forgot-password"
            className="mt-6 inline-flex items-center gap-2 rounded-lg px-1 text-sm font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Request a new link
          </Link>
        </GlassPanel>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[520px] flex-col px-4 py-16 sm:px-6">
      <GlassPanel>
        <AgentVerseLockup className="mb-6" />

        <h1 className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight text-white">
          <Lock className="size-5 text-[#c084fc]" aria-hidden="true" />
          Set a new password
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[#a8a2c8]">
          Choose a new password for your account.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
          <AuthField
            label="New password"
            icon={Lock}
            revealable
            autoComplete="new-password"
            placeholder="Enter a new password"
            error={errors.password?.message}
            {...register("password")}
          />

          <AnimatePresence mode="wait">
            {formError && (
              <motion.p
                key={formError}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                role="alert"
                className="rounded-lg border border-[#f4655b]/30 bg-[#f4655b]/10 px-3 py-2 text-xs text-[#f4655b]"
              >
                {formError}
              </motion.p>
            )}
          </AnimatePresence>

          <GradientButton
            type="submit"
            pending={isSubmitting}
            pendingLabel="Saving…"
            className="mt-1"
          >
            Reset password
          </GradientButton>
        </form>
      </GlassPanel>
    </div>
  );
}
