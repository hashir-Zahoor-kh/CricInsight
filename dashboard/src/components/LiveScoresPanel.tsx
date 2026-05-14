import { useLiveScores } from "../hooks/useApi";
import type { LiveMatch } from "../api/types";

/**
 * Live scores panel — polls every 60s, shows in-progress matches.
 *
 * Three states:
 *   loading  → shimmer skeleton row
 *   unavailable (no key / API down) → muted "no live data" notice
 *   matches  → one card per match, green pulsing dot on LIVE matches
 */
export function LiveScoresPanel() {
  const { data, isLoading } = useLiveScores();

  return (
    <section className="border-t border-line bg-canvas">
      <div className="mx-auto w-full max-w-[1440px] px-12 py-12">
        <div className="mb-6 flex items-center gap-3">
          <h2 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
            Live scores
          </h2>
          {data?.live_available && data.matches.length > 0 && (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
            </span>
          )}
        </div>

        {isLoading ? (
          <SkeletonRow />
        ) : !data?.live_available || data.matches.length === 0 ? (
          <UnavailableNotice />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.matches.map((m) => (
              <MatchCard key={m.match_id} match={m} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

// ----------------------------------------------------------------

function MatchCard({ match }: { match: LiveMatch }) {
  return (
    <div className="border border-line bg-surface p-4 transition-colors duration-150 hover:border-[#333333]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-sans text-xs font-medium text-fg">
            {match.name}
          </p>
          {match.venue && (
            <p className="mt-0.5 truncate font-mono text-[10px] text-fg-muted">
              {match.venue}
            </p>
          )}
        </div>
        {match.is_live && (
          <span className="flex-shrink-0 border border-green-500/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-green-400">
            Live
          </span>
        )}
      </div>

      {Object.keys(match.scores).length > 0 && (
        <div className="mt-3 space-y-1">
          {match.teams.map((team) =>
            match.scores[team] ? (
              <div key={team} className="flex items-baseline justify-between gap-2">
                <span className="truncate font-sans text-[11px] text-fg-secondary">
                  {team}
                </span>
                <span className="flex-shrink-0 font-mono text-[11px] tabular-nums text-fg">
                  {match.scores[team]}
                </span>
              </div>
            ) : null
          )}
        </div>
      )}

      <p className="mt-3 font-sans text-[10px] text-fg-muted">{match.status}</p>
    </div>
  );
}

function UnavailableNotice() {
  return (
    <p className="font-mono text-[11px] uppercase tracking-widest text-fg-muted">
      No live matches right now
    </p>
  );
}

function SkeletonRow() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="border border-line bg-surface p-4">
          <div className="shimmer h-3 w-3/4" />
          <div className="shimmer mt-2 h-2 w-1/2 opacity-60" />
          <div className="shimmer mt-4 h-2 w-full opacity-40" />
        </div>
      ))}
    </div>
  );
}
