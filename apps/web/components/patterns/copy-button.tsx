"use client";

import { Check, Copy } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/**
 * Copies a value and confirms it inline for ~2s.
 *
 * The inline check is the primary feedback rather than only a toast: for
 * a repeated action like copying an ID, a toast stack is noise, while
 * the button itself changing state is unambiguous and local.
 */
export function CopyButton({
  value,
  label = "Copy",
  size = "icon-sm",
}: {
  value: string;
  label?: string;
  size?: "icon-xs" | "icon-sm" | "icon";
}): React.JSX.Element {
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <Button
      type="button"
      variant="ghost"
      size={size}
      aria-label={copied ? "Copied" : label}
      onClick={() => {
        void navigator.clipboard
          .writeText(value)
          .then(() => setCopied(true))
          .catch(() => toast.error("Could not copy — your browser blocked clipboard access."));
      }}
    >
      {copied ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}
