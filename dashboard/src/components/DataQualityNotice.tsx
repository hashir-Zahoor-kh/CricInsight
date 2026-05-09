import { AlertTriangle } from "lucide-react";

import type { DataQualityWarning } from "../api/types";

/**
 * Renders the `data_quality` warnings the API attaches when a player
 * has fewer than 5 innings in the requested format. Per the contract:
 * the data is still shown alongside the notice (the dashboard never
 * hides thin data, just flags it).
 */
export function DataQualityNotice({
  warnings,
}: {
  warnings: DataQualityWarning[];
}) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="h-5 w-5 flex-shrink-0 text-amber-600"
          aria-hidden
        />
        <div className="flex-1 text-sm">
          <p className="font-semibold text-amber-900">
            Insufficient data — interpret carefully
          </p>
          <ul className="mt-1 space-y-0.5 text-amber-800">
            {warnings.map((w) => (
              <li key={w.code}>{w.message}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
