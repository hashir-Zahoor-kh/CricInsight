import { motion } from "framer-motion";

import type { FormGuideEntry, PlayerProfileCard } from "../api/types";

/**
 * Last-10-innings sparkline rendered as a hand-rolled SVG path so
 * Framer Motion can animate `pathLength` from 0 → 1 on mount. The
 * X-axis is innings index (most-recent on the right); the Y-axis
 * is runs for batters / wickets for bowlers.
 *
 * Visual tokens:
 *   - Card chrome: bg-surface, 1px line border, no shadow.
 *   - Stroke colour comes from the parent (neon lime for P1, primary
 *     green for P2) so the two halves of Row 3 stay visually paired
 *     with their respective radar polygon.
 *
 * `delay` is the staggered entry offset (P1 = 0, P2 = 0.3) called out
 * in the Bento animations spec.
 */
export function FormSparkline({
  entries,
  profile,
  accentColor = "#CCFF00",
  delay = 0,
}: {
  entries: FormGuideEntry[];
  profile: PlayerProfileCard;
  accentColor?: string;
  delay?: number;
}) {
  const useBowling = profile.primary_role === "bowler";

  // Reverse so most-recent innings is on the right — matches how
  // cricket fans naturally read form (left = older).
  const values = [...entries]
    .reverse()
    .map((e) => (useBowling ? (e.bowling_wickets ?? 0) : (e.batting_runs ?? 0)));

  const yLabel = useBowling ? "WICKETS" : "RUNS";

  return (
    <div className="border border-line bg-surface p-6">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="truncate font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Last {entries.length} {useBowling ? "spells" : "innings"} ·{" "}
          {profile.name}
        </h3>
        <span className="flex-shrink-0 font-mono text-[10px] uppercase tracking-widest text-fg-muted">
          {yLabel}
        </span>
      </div>

      {entries.length === 0 ? (
        <div className="mt-4 flex h-[120px] items-center justify-center border border-line text-xs uppercase tracking-widest text-fg-muted">
          No recent innings in this format.
        </div>
      ) : (
        <AnimatedSparklinePath
          values={values}
          accentColor={accentColor}
          delay={delay}
        />
      )}
    </div>
  );
}

// --------------------------------------------------------------- helpers

/** SVG dimensions are in viewBox units; preserveAspectRatio="none"
 *  stretches the path to the rendered width. `vector-effect=
 *  non-scaling-stroke` keeps the stroke a constant pixel width
 *  regardless of viewport stretch. */
const VB_WIDTH = 300;
const VB_HEIGHT = 100;
const PAD_X = 4;
const PAD_Y = 8;

function AnimatedSparklinePath({
  values,
  accentColor,
  delay,
}: {
  values: number[];
  accentColor: string;
  delay: number;
}) {
  const max = Math.max(...values, 1);
  const range = max; // min anchored at 0 — keeps the baseline meaningful
  const stepX =
    values.length > 1 ? (VB_WIDTH - 2 * PAD_X) / (values.length - 1) : 0;

  const points = values.map((v, i) => {
    const x = PAD_X + i * stepX;
    const y =
      VB_HEIGHT - PAD_Y - (v / range) * (VB_HEIGHT - 2 * PAD_Y);
    return [x, y] as const;
  });

  const pathD =
    "M " +
    points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" L ");

  return (
    <svg
      viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
      preserveAspectRatio="none"
      className="mt-4 h-[120px] w-full"
      aria-hidden
    >
      <motion.path
        d={pathD}
        stroke={accentColor}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1.2, delay, ease: "easeOut" }}
      />
    </svg>
  );
}
