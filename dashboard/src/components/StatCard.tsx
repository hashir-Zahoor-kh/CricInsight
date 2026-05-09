import type { ReactNode } from "react";

/**
 * Single stat tile used in stat-grid rows on the comparison and
 * player pages. The compare-mode variant accepts two values and
 * highlights whichever is higher.
 */
export function StatCard({
  label,
  value,
  hint,
  emphasis = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  emphasis?: "neutral" | "winner";
}) {
  return (
    <div
      className={`rounded-xl border p-4 ${
        emphasis === "winner"
          ? "border-pk-300 bg-pk-50 ring-1 ring-pk-200"
          : "border-ink-200 bg-white"
      }`}
    >
      <div className="text-xs font-medium uppercase tracking-wider text-ink-500">
        {label}
      </div>
      <div
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          emphasis === "winner" ? "text-pk-900" : "text-ink-900"
        }`}
      >
        {value}
      </div>
      {hint != null && (
        <div className="mt-0.5 text-xs text-ink-500">{hint}</div>
      )}
    </div>
  );
}

/**
 * Side-by-side stat row for the comparison page. Highlights the higher
 * value (or lower, if `betterIsLower` — for bowling average / economy
 * where smaller numbers mean a better player).
 */
export function CompareStatRow({
  label,
  player1,
  player2,
  format = (v) => v.toString(),
  betterIsLower = false,
  unit,
}: {
  label: string;
  player1: number | null;
  player2: number | null;
  format?: (v: number) => string;
  betterIsLower?: boolean;
  unit?: string;
}) {
  const p1Wins =
    player1 != null &&
    player2 != null &&
    (betterIsLower ? player1 < player2 : player1 > player2);
  const p2Wins =
    player1 != null &&
    player2 != null &&
    (betterIsLower ? player2 < player1 : player2 > player1);

  return (
    <div className="grid grid-cols-3 items-center border-b border-ink-100 py-3 last:border-b-0">
      <div className="text-sm font-medium text-ink-700">{label}</div>
      <div
        className={`text-right text-lg tabular-nums ${
          p1Wins ? "font-semibold text-pk-900" : "text-ink-700"
        }`}
      >
        {player1 != null ? format(player1) : "—"}
        {unit != null && player1 != null && (
          <span className="ml-1 text-xs text-ink-400">{unit}</span>
        )}
      </div>
      <div
        className={`text-right text-lg tabular-nums ${
          p2Wins ? "font-semibold text-pk-900" : "text-ink-700"
        }`}
      >
        {player2 != null ? format(player2) : "—"}
        {unit != null && player2 != null && (
          <span className="ml-1 text-xs text-ink-400">{unit}</span>
        )}
      </div>
    </div>
  );
}
