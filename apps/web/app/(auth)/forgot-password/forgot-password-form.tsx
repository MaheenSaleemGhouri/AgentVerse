"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, CheckCircle2, KeyRound, Mail } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AgentVerseLockup } from "@/components/auth/agentverse-mark";
import { AuthField } from "@/components/auth/auth-field";
import { GradientButton } from "@/components/auth/auth-buttons";
import { GlassPanel } from "@/components/auth/glass-panel";
import { authClient } from "@/lib/auth-client";

const schema = z.object({
  email: z.string().min(1, "Email is required.").email("Enter a valid email address."),
});
type FormValues = z.infer<typeof schema>;

/**
 * Requests a reset link via Better Auth's `requestPasswordReset`, which
 * always returns the same success response whether or not the email
 * belongs to an account (§10 — never leak account existence). The
 * confirmation state below mirrors that uniformity rather than branching
 * on it.
 */
export function ForgotPasswordForm(): React.JSX.Element {
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  async function onSubmit(values: FormValues): Promise<void> {
    setFormError(null);
    const { error } = await authClient.requestPasswordReset({
      email: values.email,
      redirectTo: "/reset-password",
    });
    if (error) {
      setFormError(error.message ?? "Could not send the reset email. Try again.");
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <div className="mx-auto flex w-full max-w-[520px] flex-col px-4 py-16 sm:px-6">
        <GlassPanel>
          <AgentVerseLockup className="mb-6" />
          <h1 className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight text-white">
            <CheckCircle2 className="size-5 text-[#c084fc]" aria-hidden="true" />
            Check your email
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-[#a8a2c8]">
            If that email has an AgentVerse account, a reset link is on its way. It expires in
            an hour.
          </p>
          <Link
            href="/login"
            className="mt-6 inline-flex items-center gap-2 rounded-lg px-1 text-sm font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to login
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
          <KeyRound className="size-5 text-[#c084fc]" aria-hidden="true" />
          Reset your password
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[#a8a2c8]">
          Enter the email on your account and we&apos;ll send a link to reset your password.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
          <AuthField
            label="Email"
            icon={Mail}
            type="email"
            autoComplete="email"
            placeholder="Enter your email"
            error={errors.email?.message}
            {...register("email")}
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

          <GradientButton type="submit" pending={isSubmitting} pendingLabel="Sending…" className="mt-1">
            Send reset link
          </GradientButton>
        </form>

        <Link
          href="/login"
          className="mt-6 inline-flex items-center gap-2 rounded-lg px-1 text-sm font-medium text-[#c084fc] transition-colors hover:text-[#d8b4fe] focus:outline-none focus-visible:ring-[3px] focus-visible:ring-[#a855f7]/40"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to login
        </Link>
      </GlassPanel>
    </div>
  );
}
