/** Lightweight loading placeholder — preserves layout so the page
 *  doesn't reflow when data arrives. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-ink-100 ${className}`}
      aria-hidden
    />
  );
}

/** Page-level skeleton for full sections. */
export function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-64 w-full" />
      <div className="grid grid-cols-4 gap-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    </div>
  );
}
