import { AlertTriangle } from "lucide-react";

import type { DataQualityWarning } from "../api/types";

/**
 * Renders the `data_quality` warnings the API attaches when a player
 * has fewer than 5 innings in the requested format. Per the contract:
 * the data is still shown alongside the notice (the dashboard never
 * hides thin data, just flags it).
 *
 * Dark-theme amber treatment — translucent fill over the canvas so
 * the warning sits adjacent to (not on top of) the surrounding cards.
 */
export function DataQualityNotice({
  warnings,
}: {
  warnings: DataQualityWarning[];
}) {
  if (warnings.length === 0) return null;
  return (
    <div className="border border-amber-500/40 bg-amber-500/[0.04] p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="h-5 w-5 flex-shrink-0 text-amber-400"
          aria-hidden
        />
        <div className="flex-1">
          <p className="font-sans text-[11px] uppercase tracking-widest text-amber-300">
            Insufficient data — interpret carefully
          </p>
          <ul className="mt-2 space-y-0.5 font-sans text-sm text-amber-100/80">
            {warnings.map((w) => (
              <li key={w.code}>{w.message}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
