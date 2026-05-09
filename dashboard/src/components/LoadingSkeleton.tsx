/** Lightweight loading placeholder — preserves layout so the page
 *  doesn't reflow when data arrives. Uses Tailwind's `animate-pulse`
 *  on `bg-ink-200` blocks per the Phase 5.4 polish contract. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-ink-200 ${className}`}
      aria-hidden
    />
  );
}

/** Page-level skeleton for full sections (loose layout). */
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
// Content-shaped skeletons. The shapes mirror the rendered components
// closely enough that there's zero layout shift when real data arrives.
// --------------------------------------------------------------------

/** Mirrors `PlayerProfileCard` — pk-900 hero card with name, country
 *  chip, and style badges. */
export function ProfileCardSkeleton() {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-pk-900 p-6 shadow-card">
      <div className="absolute right-0 top-0 h-1 w-full bg-pk-600" aria-hidden />
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <div className="h-3 w-20 animate-pulse rounded bg-pk-700" />
          <div className="h-7 w-48 animate-pulse rounded bg-pk-700" />
          <div className="h-4 w-24 animate-pulse rounded bg-pk-800" />
        </div>
        <div className="h-8 w-8 animate-pulse rounded-full bg-pk-700" />
      </div>
      <div className="mt-5 flex gap-2">
        <div className="h-5 w-28 animate-pulse rounded-full bg-white/10" />
        <div className="h-5 w-24 animate-pulse rounded-full bg-white/10" />
      </div>
    </div>
  );
}

/** Mirrors `ComparisonRadar` — header row + 360 px chart area. */
export function RadarSkeleton() {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <div className="mb-4 flex items-baseline justify-between">
        <div className="h-5 w-40 animate-pulse rounded bg-ink-200" />
        <div className="h-3 w-24 animate-pulse rounded bg-ink-100" />
      </div>
      <div className="flex h-[360px] items-center justify-center">
        <div className="relative h-[260px] w-[260px]">
          {/* Concentric pulse rings hint at the radar shape so the
              skeleton reads as "chart loading", not "blank circle". */}
          <div className="absolute inset-0 animate-pulse rounded-full bg-ink-100" />
          <div className="absolute inset-6 animate-pulse rounded-full bg-ink-200/70" />
          <div className="absolute inset-14 animate-pulse rounded-full bg-ink-200" />
        </div>
      </div>
    </div>
  );
}

/** Mirrors the side-by-side stat table on the comparison page —
 *  header row + 6 stat rows. */
export function StatTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <div className="mb-2 space-y-1.5">
        <div className="h-4 w-32 animate-pulse rounded bg-ink-200" />
        <div className="h-3 w-56 animate-pulse rounded bg-ink-100" />
      </div>
      <div className="grid grid-cols-3 gap-3 border-b border-ink-200 pb-2">
        <div className="h-3 w-12 animate-pulse rounded bg-ink-100" />
        <div className="h-3 w-20 ml-auto animate-pulse rounded bg-ink-100" />
        <div className="h-3 w-20 ml-auto animate-pulse rounded bg-ink-100" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-3 items-center gap-3 border-b border-ink-100 py-3 last:border-b-0"
        >
          <div className="h-4 w-24 animate-pulse rounded bg-ink-200" />
          <div className="h-5 w-16 ml-auto animate-pulse rounded bg-ink-200" />
          <div className="h-5 w-16 ml-auto animate-pulse rounded bg-ink-200" />
        </div>
      ))}
    </div>
  );
}

/** Mirrors `FormSparkline` — header + chart strip. */
export function SparklineSkeleton() {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <div className="flex items-baseline justify-between">
        <div className="h-3 w-40 animate-pulse rounded bg-ink-200" />
        <div className="h-3 w-12 animate-pulse rounded bg-ink-100" />
      </div>
      <div className="mt-4 h-[140px] animate-pulse rounded-md bg-ink-100" />
    </div>
  );
}
