import { Globe, ShieldCheck, Trophy } from "lucide-react";

import type { PlayerProfileCard as ProfileCardType } from "../api/types";

const ROLE_LABEL: Record<string, string> = {
  batsman: "Batsman",
  bowler: "Bowler",
  allrounder: "All-rounder",
  wicketkeeper: "Wicketkeeper",
};

/**
 * Big profile card used at the top of each comparison slot.
 * Lead colour is `pk-900` so the two cards sit visually above the
 * lighter content below them — the page reads top-down: who → stats.
 */
export function PlayerProfileCard({
  profile,
  accent = "primary",
}: {
  profile: ProfileCardType;
  accent?: "primary" | "secondary";
}) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl shadow-card ${
        accent === "primary" ? "bg-pk-900 text-white" : "bg-white text-ink-900"
      }`}
    >
      {/* Decorative corner stripe — subtle nod to the flag without
          getting kitsch. */}
      <div
        className={`absolute right-0 top-0 h-1 w-full ${
          accent === "primary" ? "bg-pk-600" : "bg-pk-900"
        }`}
        aria-hidden
      />
      <div className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <div
              className={`text-xs font-medium uppercase tracking-wider ${
                accent === "primary" ? "text-pk-200" : "text-ink-500"
              }`}
            >
              {ROLE_LABEL[profile.primary_role] ?? profile.primary_role}
            </div>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              {profile.name}
            </h2>
            {profile.country != null && (
              <div
                className={`mt-2 flex items-center gap-1.5 text-sm ${
                  accent === "primary" ? "text-pk-100" : "text-ink-600"
                }`}
              >
                <Globe className="h-3.5 w-3.5" aria-hidden />
                {profile.country}
              </div>
            )}
          </div>
          <Trophy
            className={`h-8 w-8 ${
              accent === "primary" ? "text-pk-300" : "text-pk-700"
            }`}
            aria-hidden
          />
        </div>

        <div
          className={`mt-5 flex flex-wrap gap-2 text-xs ${
            accent === "primary" ? "text-pk-100" : "text-ink-600"
          }`}
        >
          {profile.batting_style != null && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${
                accent === "primary" ? "bg-white/10" : "bg-pk-50 text-pk-900"
              }`}
            >
              <ShieldCheck className="h-3 w-3" aria-hidden />
              {profile.batting_style}
            </span>
          )}
          {profile.bowling_style != null && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${
                accent === "primary" ? "bg-white/10" : "bg-pk-50 text-pk-900"
              }`}
            >
              <ShieldCheck className="h-3 w-3" aria-hidden />
              {profile.bowling_style}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
