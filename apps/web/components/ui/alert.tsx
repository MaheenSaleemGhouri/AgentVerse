import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const alertVariants = cva(
  "relative grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 rounded-lg border px-4 py-3 text-sm [&>svg]:size-4 [&>svg]:translate-y-0.5",
  {
    variants: {
      // Same semantic vocabulary as Badge and Progress — a "danger"
      // alert and a "danger" usage meter resolve to the same token.
      tone: {
        default: "border-border bg-card text-card-foreground [&>svg]:text-muted-foreground",
        info: "border-info/30 bg-info-soft text-foreground [&>svg]:text-info",
        success: "border-success/30 bg-success-soft text-foreground [&>svg]:text-success",
        warning: "border-warning/30 bg-warning-soft text-foreground [&>svg]:text-warning",
        danger:
          "border-destructive/30 bg-destructive-soft text-foreground [&>svg]:text-destructive",
      },
    },
    defaultVariants: { tone: "default" },
  }
)

function Alert({
  className,
  tone,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div data-slot="alert" role="alert" className={cn(alertVariants({ tone }), className)} {...props} />
}

function AlertTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-title"
      className={cn("col-start-2 font-medium tracking-tight", className)}
      {...props}
    />
  )
}

function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-description"
      className={cn("col-start-2 text-sm text-muted-foreground [&_p]:leading-relaxed", className)}
      {...props}
    />
  )
}

export { Alert, AlertTitle, AlertDescription, alertVariants }
