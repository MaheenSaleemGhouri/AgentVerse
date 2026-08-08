import { cn } from "@/lib/utils"

/**
 * `motion-safe:` scopes the pulse to users who haven't asked for
 * reduced motion (CLAUDE.md §15/§27) — this is the single primitive
 * every skeleton in the product is built from, so fixing it once here
 * fixes every loading state at once rather than needing the same guard
 * copied into each screen that uses it.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("motion-safe:animate-pulse rounded-md bg-accent", className)}
      {...props}
    />
  )
}

export { Skeleton }
