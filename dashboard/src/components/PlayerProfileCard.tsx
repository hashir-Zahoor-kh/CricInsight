import rankingsData from "../data/icc_rankings.json";
import type { PlayerProfileCard as ProfileCardType, PlayerRole } from "../api/types";

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

      <RankingBadges name={profile.name} />
    </div>
  );
}

// ----------------------------------------------------------------

type RankingEntry = Record<string, number>;
const players = rankingsData.players as Record<string, RankingEntry>;

const FORMAT_LABEL: Record<string, string> = {
  t20i_batting:  "T20I BAT",
  t20i_bowling:  "T20I BOWL",
  odi_batting:   "ODI BAT",
  odi_bowling:   "ODI BOWL",
  test_batting:  "TEST BAT",
  test_bowling:  "TEST BOWL",
};

function RankingBadges({ name }: { name: string }) {
  const entry = players[name];
  if (!entry) return <div className="mt-auto pt-6" aria-hidden />;

  const badges = Object.entries(entry) as [string, number][];

  return (
    <div className="mt-auto flex flex-wrap gap-2 pt-4">
      {badges.map(([key, rank]) => (
        <span
          key={key}
          className="border border-accent px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest text-accent"
        >
          #{rank} {FORMAT_LABEL[key] ?? key}
        </span>
      ))}
    </div>
  );
}
