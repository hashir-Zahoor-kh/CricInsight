/** Lightweight loading placeholder — preserves layout so the page
 *  doesn't reflow when data arrives. Dark theme uses an `elevated`
 *  block over `surface` (a more polished shimmer animation is the
 *  Visual Redesign step 9 target). */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse bg-elevated ${className}`}
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
// Content-shaped skeletons. The shapes mirror the rendered Bento Grid
// rows closely enough that there's zero layout shift when real data
// arrives.
// --------------------------------------------------------------------

/** Mirrors the dark `PlayerProfileCard` — title row + country line. */
export function ProfileCardSkeleton() {
  return (
    <div className="min-h-[140px] border border-line bg-surface p-6">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="h-10 w-64 animate-pulse bg-elevated" />
          <div className="h-3 w-24 animate-pulse bg-elevated/70" />
        </div>
        <div className="h-6 w-12 animate-pulse bg-elevated" />
      </div>
    </div>
  );
}

/** Mirrors `ComparisonRadar` — header row + 360 px chart area. */
export function RadarSkeleton() {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="mb-4 flex items-baseline justify-between">
        <div className="h-3 w-32 animate-pulse bg-elevated" />
        <div className="h-3 w-20 animate-pulse bg-elevated/70" />
      </div>
      <div className="flex h-[360px] items-center justify-center">
        <div className="relative h-[260px] w-[260px]">
          {/* Concentric pulse rings hint at the radar shape so the
              skeleton reads as "chart loading", not "blank circle". */}
          <div className="absolute inset-0 animate-pulse rounded-full bg-elevated/60" />
          <div className="absolute inset-6 animate-pulse rounded-full bg-elevated/40" />
          <div className="absolute inset-14 animate-pulse rounded-full bg-elevated/25" />
        </div>
      </div>
    </div>
  );
}

/** Mirrors the legacy career stat-table card on PlayerPage —
 *  still used until PlayerPage is redesigned in Visual Redesign
 *  step 10. */
export function StatTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="mb-3 space-y-1.5">
        <div className="h-4 w-32 animate-pulse bg-elevated" />
        <div className="h-3 w-56 animate-pulse bg-elevated/70" />
      </div>
      <div className="grid grid-cols-3 gap-3 border-b border-line pb-2">
        <div className="h-3 w-12 animate-pulse bg-elevated/70" />
        <div className="ml-auto h-3 w-20 animate-pulse bg-elevated/70" />
        <div className="ml-auto h-3 w-20 animate-pulse bg-elevated/70" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="grid grid-cols-3 items-center gap-3 border-b border-line py-3 last:border-b-0"
        >
          <div className="h-4 w-24 animate-pulse bg-elevated" />
          <div className="ml-auto h-5 w-16 animate-pulse bg-elevated" />
          <div className="ml-auto h-5 w-16 animate-pulse bg-elevated" />
        </div>
      ))}
    </div>
  );
}

/** Mirrors the narrow key-stat card — label, big number, sublabel. */
export function KeyStatSkeleton() {
  return (
    <div className="flex min-h-[260px] flex-col justify-between border border-line bg-surface p-6">
      <div className="h-3 w-16 animate-pulse bg-elevated" />
      <div className="h-12 w-24 animate-pulse bg-elevated" />
      <div className="h-3 w-20 animate-pulse bg-elevated/70" />
    </div>
  );
}

/** Mirrors `FormSparkline` — header + chart strip. */
export function SparklineSkeleton() {
  return (
    <div className="border border-line bg-surface p-6">
      <div className="flex items-baseline justify-between">
        <div className="h-3 w-40 animate-pulse bg-elevated" />
        <div className="h-3 w-12 animate-pulse bg-elevated/70" />
      </div>
      <div className="mt-4 h-[120px] animate-pulse bg-elevated/40" />
    </div>
  );
}

/** Mirrors the common-opponents table — header + N row stripes. */
export function OpponentsTableSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="border border-line bg-surface">
      <div className="border-b border-line p-6">
        <div className="h-3 w-48 animate-pulse bg-elevated" />
      </div>
      <div>
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className={`grid grid-cols-3 gap-4 px-6 py-3 ${
              i % 2 === 0 ? "bg-surface" : "bg-canvas"
            }`}
          >
            <div className="h-3 w-20 animate-pulse bg-elevated" />
            <div className="ml-auto h-3 w-16 animate-pulse bg-elevated" />
            <div className="ml-auto h-3 w-16 animate-pulse bg-elevated" />
          </div>
        ))}
      </div>
    </div>
  );
}
