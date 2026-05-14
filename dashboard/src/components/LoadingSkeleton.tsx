/** Shimmer skeleton primitives — base #111111, highlight #1A1A1A,
 *  left-to-right sweep via the `.shimmer` utility in index.css. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`shimmer ${className}`} aria-hidden />;
}

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

// --------------------------------------------------------------------
// Content-shaped skeletons — shapes mirror actual Bento Grid rows.
// --------------------------------------------------------------------

/** Mirrors `PlayerProfileCard` — title block + country line + role chip. */
export function ProfileCardSkeleton() {
  return (
    <div className="min-h-[140px] border border-line bg-surface p-6">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="shimmer h-10 w-64" />
          <div className="shimmer h-3 w-24 opacity-70" />
        </div>
        <div className="shimmer h-6 w-12" />
      </div>
    </div>
  );
}

/** Mirrors `ComparisonRadar` — header + concentric ring hint. */
export function RadarSkeleton() {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="mb-4 flex items-baseline justify-between">
        <div className="shimmer h-3 w-32" />
        <div className="shimmer h-3 w-20 opacity-70" />
      </div>
      <div className="flex h-[360px] items-center justify-center">
        <div className="relative h-[260px] w-[260px]">
          <div className="shimmer absolute inset-0 rounded-full opacity-60" />
          <div className="shimmer absolute inset-6 rounded-full opacity-40" />
          <div className="shimmer absolute inset-14 rounded-full opacity-25" />
        </div>
      </div>
    </div>
  );
}

/** Mirrors the career stat-table on `PlayerPage`. */
export function StatTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="mb-3 space-y-1.5">
        <div className="shimmer h-4 w-32" />
        <div className="shimmer h-3 w-56 opacity-70" />
      </div>
      <div className="grid grid-cols-3 gap-3 border-b border-line pb-2">
        <div className="shimmer h-3 w-12 opacity-70" />
        <div className="shimmer ml-auto h-3 w-20 opacity-70" />
        <div className="shimmer ml-auto h-3 w-20 opacity-70" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-3 items-center gap-3 border-b border-line py-3 last:border-b-0"
        >
          <div className="shimmer h-4 w-24" />
          <div className="shimmer ml-auto h-5 w-16" />
          <div className="shimmer ml-auto h-5 w-16" />
        </div>
      ))}
    </div>
  );
}

/** Mirrors the narrow `KeyStatCard` — label, big number, name. */
export function KeyStatSkeleton() {
  return (
    <div className="flex min-h-[260px] flex-col justify-between border border-line bg-surface p-6">
      <div className="shimmer h-3 w-16" />
      <div className="shimmer h-12 w-24" />
      <div className="shimmer h-3 w-20 opacity-70" />
    </div>
  );
}

/** Mirrors `FormSparkline` — header + chart strip. */
export function SparklineSkeleton() {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="flex items-baseline justify-between">
        <div className="shimmer h-3 w-40" />
        <div className="shimmer h-3 w-12 opacity-70" />
      </div>
      <div className="shimmer mt-4 h-[120px] opacity-40" />
    </div>
  );
}

/** Mirrors the common-opponents table — header + N zebra rows. */
export function OpponentsTableSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="border border-line bg-surface">
      <div className="border-b border-line p-6">
        <div className="shimmer h-3 w-48" />
      </div>
      <div>
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className={`grid grid-cols-3 gap-4 px-6 py-3 ${
              i % 2 === 0 ? "bg-surface" : "bg-canvas"
            }`}
          >
            <div className="shimmer h-3 w-20" />
            <div className="shimmer ml-auto h-3 w-16" />
            <div className="shimmer ml-auto h-3 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}
