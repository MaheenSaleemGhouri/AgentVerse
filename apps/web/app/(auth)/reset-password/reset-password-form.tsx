"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthLockup } from "@/components/auth/auth-lockup";
import { AuthSubmitButton } from "@/components/auth/auth-buttons";
import { AuthField } from "@/components/auth/auth-field";
import { AuthPanel } from "@/components/auth/auth-panel";
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
      <div className="mx-auto flex w-full max-w-[480px] flex-col px-4 py-16 sm:px-6">
        <AuthPanel elevated>
          <AuthLockup className="mb-6" />
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Link expired</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            This reset link is invalid or has already been used. Request a new one.
          </p>
          <Link
            href="/forgot-password"
            className="mt-6 inline-flex items-center gap-2 rounded px-1 text-sm font-medium text-primary transition-colors hover:underline focus:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Request a new link
          </Link>
        </AuthPanel>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[480px] flex-col px-4 py-16 sm:px-6">
      <AuthPanel elevated>
        <AuthLockup className="mb-6" />

        <h1 className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight text-foreground">
          <Lock className="size-5 text-primary" aria-hidden="true" />
          Set a new password
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
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
                className="rounded-md border border-destructive/30 bg-destructive-soft px-3 py-2 text-xs text-destructive-strong"
              >
                {formError}
              </motion.p>
            )}
          </AnimatePresence>

          <AuthSubmitButton pending={isSubmitting} pendingLabel="Saving…" className="mt-1">
            Reset password
          </AuthSubmitButton>
        </form>
      </AuthPanel>
    </div>
  );
}
