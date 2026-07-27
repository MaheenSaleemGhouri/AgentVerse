"use client";

import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { cn } from "@/lib/utils";

import { Card } from "@/components/ui/card";

const THEMES = [
  { value: "light", label: "Light", icon: Sun, description: "Bright surfaces, dark text" },
  { value: "dark", label: "Dark", icon: Moon, description: "The default AgentVerse look" },
  {
    value: "system",
    label: "System",
    icon: Monitor,
    description: "Follow your operating system",
  },
] as const;

export function AppearancePanel(): React.JSX.Element {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => setMounted(true), []);

  return (
    <div className="max-w-2xl space-y-6">
      <Card className="gap-4 p-6">
        <div>
          <h2 className="font-medium">Theme</h2>
          <p className="text-sm text-muted-foreground">
            Applies immediately and is remembered on this device.
          </p>
        </div>

        <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <legend className="sr-only">Theme</legend>
          {THEMES.map((option) => {
            const Icon = option.icon;
            const isSelected = mounted && theme === option.value;
            return (
              <label
                key={option.value}
                className={cn(
                  "relative flex cursor-pointer flex-col gap-2 rounded-lg border p-4 transition-colors",
                  "focus-within:ring-[3px] focus-within:ring-ring/50",
                  isSelected
                    ? "border-primary bg-accent/40"
                    : "border-border hover:border-primary/40"
                )}
              >
                <input
                  type="radio"
                  name="theme"
                  value={option.value}
                  checked={isSelected}
                  onChange={() => setTheme(option.value)}
                  className="sr-only"
                />
                <span className="flex items-center justify-between">
                  <Icon className="size-4" aria-hidden="true" />
                  {isSelected && <Check className="size-4 text-primary" aria-hidden="true" />}
                </span>
                <span className="text-sm font-medium">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.description}</span>
              </label>
            );
          })}
        </fieldset>
      </Card>

      <Card className="gap-2 p-6">
        <h2 className="font-medium">Motion</h2>
        <p className="text-sm text-muted-foreground">
          AgentVerse honours your system&apos;s reduced-motion setting automatically. Turn it on in
          your OS accessibility preferences and non-essential animation stops everywhere in the
          product.
        </p>
      </Card>
    </div>
  );
}
