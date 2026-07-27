import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shared loading boundary for every workspace route.
 *
 * Skeletons that echo the real page rhythm (header, stat row, content
 * grid) rather than a centred spinner — the layout does not jump when
 * data arrives, and the wait communicates what is coming.
 */
export default function WorkspaceLoading(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-8" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>

      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-xl" />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    </div>
  );
}
