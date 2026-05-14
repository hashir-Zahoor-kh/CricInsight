import type { PlayerProfileCard as ProfileCardType, PlayerRole } from "../api/types";

/**
 * Row-1 header card for the Bento Grid. Identity-only — no inline
 * stats. Layout:
 *   ┌───────────────────────────────────────────────────────┐
 *   │ NAME (Bebas Neue 48px)                       BAT/BOWL │
 *   │ COUNTRY (DM Sans uppercase, secondary)                │
 *   │                                                       │
 *   │ #-- T20I  ← TODO Feature 4 (ICC ranking pill)         │
 *   └───────────────────────────────────────────────────────┘
 */
const ROLE_BADGE: Record<PlayerRole, string> = {
  batsman: "BAT",
  bowler: "BOWL",
  allrounder: "ALL",
  wicketkeeper: "WK",
};

export function PlayerProfileCard({
  profile,
}: {
  profile: ProfileCardType;
}) {
  return (
    <div className="relative flex min-h-[140px] flex-col border border-line bg-surface p-6 transition-colors duration-150 hover:border-[#333333]">
      <div className="flex items-start justify-between gap-4">
        <h2 className="font-display text-[48px] uppercase leading-none tracking-tight text-fg">
          {profile.name}
        </h2>
        <span className="flex-shrink-0 border border-line px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-fg-secondary">
          {ROLE_BADGE[profile.primary_role] ?? "—"}
        </span>
      </div>

      {profile.country != null && (
        <div className="mt-3 font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          {profile.country}
        </div>
      )}

      {/* TODO Feature 4: ICC ranking badge — neon-lime pill, bottom-left.
          Once src/data/icc_rankings.json exists, render something like:
            <span className="border border-accent px-2 py-0.5 font-mono
                             text-[11px] uppercase tracking-widest text-accent">
              #{rank} {format}
            </span>
          For now the slot is reserved so the card height matches the
          eventual layout. */}
      <div className="mt-auto pt-6" aria-hidden />
    </div>
  );
}
