import { useState } from "react";
import { ArrowRight, BarChart3, Sparkles, Users } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "../components/EmptyState";
import { Skeleton } from "../components/LoadingSkeleton";
import { useHealth, usePlayers, useRecentMatches } from "../hooks/useApi";
import { MatchType } from "../api/types";

/**
 * Landing page. Two-step picker: pick player 1 → pick player 2 →
 * "Compare" CTA navigates to /compare with the search-param state
 * pre-filled. Also shows a recent-matches feed so the page isn't
 * just a form.
 */
export function HomePage() {
  const navigate = useNavigate();
  const playersQuery = usePlayers({ limit: 100 });
  const matchesQuery = useRecentMatches(8);
  const health = useHealth();

  const [p1, setP1] = useState<number | null>(null);
  const [p2, setP2] = useState<number | null>(null);
  const [fmt, setFmt] = useState<MatchType>(MatchType.T20I);

  const players = playersQuery.data ?? [];
  const empty = !playersQuery.isLoading && players.length === 0;

  const canCompare = p1 != null && p2 != null && p1 !== p2;

  const onCompare = () => {
    if (!canCompare) return;
    navigate(`/compare?p1=${p1}&p2=${p2}&fmt=${fmt}`);
  };

  return (
    <div className="space-y-8">
      <Hero
        playerCount={players.length}
        matchCount={matchesQuery.data?.length ?? 0}
        apiHealthy={health.data?.status === "ok"}
      />

      {empty ? (
        <EmptyState
          title="Database is empty"
          icon={<Users className="h-6 w-6 text-pk-700" aria-hidden />}
        />
      ) : (
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 space-y-4 rounded-2xl bg-white p-6 shadow-card">
            <div>
              <h2 className="text-xl font-semibold text-ink-900">
                Compare two players
              </h2>
              <p className="text-sm text-ink-600">
                Pick any two players from the seeded roster and a format —
                we'll show side-by-side stats, form, and head-to-head.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <PlayerPicker
                label="Player 1"
                value={p1}
                onChange={setP1}
                players={players}
                excludeId={p2}
                loading={playersQuery.isLoading}
              />
              <PlayerPicker
                label="Player 2"
                value={p2}
                onChange={setP2}
                players={players}
                excludeId={p1}
                loading={playersQuery.isLoading}
              />
            </div>

            <FormatPicker value={fmt} onChange={setFmt} />

            <button
              type="button"
              onClick={onCompare}
              disabled={!canCompare}
              className="inline-flex items-center gap-2 rounded-md bg-pk-900 px-5 py-2.5 text-sm font-semibold text-white shadow-card transition-colors hover:bg-pk-700 disabled:cursor-not-allowed disabled:bg-ink-300"
            >
              Compare players
              <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          </div>

          <RecentMatchesPanel
            loading={matchesQuery.isLoading}
            error={matchesQuery.isError}
            matches={matchesQuery.data}
          />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------

function Hero({
  playerCount,
  matchCount,
  apiHealthy,
}: {
  playerCount: number;
  matchCount: number;
  apiHealthy: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-2xl bg-pk-900 p-8 text-white shadow-card">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-pk-600 p-2">
          <BarChart3 className="h-6 w-6" aria-hidden />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            CricInsight
          </h1>
          <p className="mt-1 max-w-lg text-pk-100">
            Side-by-side player comparison across formats. Pick two
            international batters, bowlers, or all-rounders and dig into
            the head-to-head.
          </p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-3 gap-3 text-sm">
        <KpiBadge label="Players" value={playerCount.toString()} />
        <KpiBadge label="Recent matches" value={matchCount.toString()} />
        <KpiBadge label="API" value={apiHealthy ? "Healthy" : "Degraded"} />
      </div>
    </div>
  );
}

function KpiBadge({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/10 px-4 py-3">
      <div className="text-[10px] font-medium uppercase tracking-wider text-pk-200">
        {label}
      </div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums text-white">
        {value}
      </div>
    </div>
  );
}

function PlayerPicker({
  label,
  value,
  onChange,
  players,
  excludeId,
  loading,
}: {
  label: string;
  value: number | null;
  onChange: (id: number | null) => void;
  players: { id: number; name: string; country: string | null }[];
  excludeId: number | null;
  loading: boolean;
}) {
  return (
    <div>
      <label className="block text-xs font-medium uppercase tracking-wider text-ink-500">
        {label}
      </label>
      <select
        className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 focus:border-pk-600 focus:outline-none focus:ring-1 focus:ring-pk-600"
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : Number(e.target.value))
        }
        disabled={loading}
      >
        <option value="">{loading ? "loading…" : "Select a player"}</option>
        {players
          .filter((p) => p.id !== excludeId)
          .map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.country ? ` · ${p.country}` : ""}
            </option>
          ))}
      </select>
    </div>
  );
}

function FormatPicker({
  value,
  onChange,
}: {
  value: MatchType;
  onChange: (fmt: MatchType) => void;
}) {
  const options: { value: MatchType; label: string }[] = [
    { value: MatchType.T20I, label: "T20I" },
    { value: MatchType.ODI, label: "ODI" },
    { value: MatchType.TEST, label: "Test" },
    { value: MatchType.T20, label: "T20 (franchise)" },
  ];
  return (
    <div>
      <label className="block text-xs font-medium uppercase tracking-wider text-ink-500">
        Format
      </label>
      <div className="mt-1 flex gap-2">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              o.value === value
                ? "bg-pk-900 text-white"
                : "bg-ink-50 text-ink-700 hover:bg-ink-100"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function RecentMatchesPanel({
  loading,
  error,
  matches,
}: {
  loading: boolean;
  error: boolean;
  matches: { id: number; team1: string; team2: string; date: string; match_type: string; winner: string | null }[] | undefined;
}) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink-900">
        <Sparkles className="h-4 w-4 text-pk-600" aria-hidden />
        Recent matches
      </h3>
      <div className="mt-3 space-y-2">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : error ? (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            Couldn't reach the API.
          </p>
        ) : matches == null || matches.length === 0 ? (
          <p className="rounded-md bg-ink-50 p-3 text-sm text-ink-500">
            No matches in the database yet.
          </p>
        ) : (
          matches.slice(0, 6).map((m) => (
            <div
              key={m.id}
              className="rounded-md border border-ink-100 px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-ink-800">
                  {m.team1} vs {m.team2}
                </span>
                <span className="text-xs uppercase tracking-wider text-pk-700">
                  {m.match_type}
                </span>
              </div>
              <div className="mt-0.5 flex items-center justify-between text-xs text-ink-500">
                <span>{new Date(m.date).toLocaleDateString()}</span>
                {m.winner && (
                  <span className="text-pk-700">{m.winner} won</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
