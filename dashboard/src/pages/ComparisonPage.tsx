import { useEffect } from "react";
import { ArrowRightLeft, Users } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { ComparisonRadar } from "../components/ComparisonRadar";
import { DataQualityNotice } from "../components/DataQualityNotice";
import { EmptyState } from "../components/EmptyState";
import { FormSparkline } from "../components/FormSparkline";
import {
  ProfileCardSkeleton,
  RadarSkeleton,
  SparklineSkeleton,
  StatTableSkeleton,
} from "../components/LoadingSkeleton";
import { PlayerProfileCard } from "../components/PlayerProfileCard";
import { CompareStatRow } from "../components/StatCard";
import { useCompare, usePlayers } from "../hooks/useApi";
import { MatchType, type PlayerComparisonSlot } from "../api/types";

/**
 * THE flagship page. Reads `player1`, `player2`, `format` from the URL
 * (so links are shareable / bookmarkable) and falls back to dropdowns
 * when any parameter is missing.
 *
 * Layout (top → bottom):
 *   1. Pickers row (player1 / player2 / format)
 *   2. Two profile cards side-by-side
 *   3. Data-quality warnings (if any)
 *   4. Radar chart — batting OR bowling depending on shared role
 *   5. Side-by-side stat row (career averages, milestones)
 *   6. Two form sparklines side by side
 *   7. Common opponents table
 */
export function ComparisonPage() {
  const [params, setParams] = useSearchParams();

  const player1Id = parseIntOrNull(params.get("p1"));
  const player2Id = parseIntOrNull(params.get("p2"));
  const formatParam = (params.get("fmt") as MatchType | null) ?? null;

  const playersQuery = usePlayers({ limit: 100 });
  const compareQuery = useCompare(player1Id, player2Id, formatParam);

  // Default the format the first time the page mounts so the user
  // doesn't have to pick T20I before any chart renders.
  useEffect(() => {
    if (formatParam == null) {
      const next = new URLSearchParams(params);
      next.set("fmt", MatchType.T20I);
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value == null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
          Player Comparison
        </h1>
        <p className="text-ink-600">
          Side-by-side career stats, form, and head-to-head insight.
        </p>
      </header>

      <PickersRow
        playersLoading={playersQuery.isLoading}
        players={playersQuery.data ?? []}
        player1Id={player1Id}
        player2Id={player2Id}
        format={formatParam}
        onPlayer1Change={(id) => updateParam("p1", id == null ? null : String(id))}
        onPlayer2Change={(id) => updateParam("p2", id == null ? null : String(id))}
        onFormatChange={(fmt) => updateParam("fmt", fmt)}
      />

      <Body
        playersEmpty={
          !playersQuery.isLoading && (playersQuery.data?.length ?? 0) === 0
        }
        loading={compareQuery.isLoading || compareQuery.isFetching}
        error={compareQuery.error}
        data={compareQuery.data}
        // The picker UX leans on the "both players + format selected"
        // gate to know whether to show the empty hint.
        hasSelection={
          player1Id != null && player2Id != null && formatParam != null
        }
      />
    </div>
  );
}

// --------------------------------------------------------------------

function PickersRow({
  playersLoading,
  players,
  player1Id,
  player2Id,
  format,
  onPlayer1Change,
  onPlayer2Change,
  onFormatChange,
}: {
  playersLoading: boolean;
  players: { id: number; name: string; country: string | null }[];
  player1Id: number | null;
  player2Id: number | null;
  format: MatchType | null;
  onPlayer1Change: (id: number | null) => void;
  onPlayer2Change: (id: number | null) => void;
  onFormatChange: (fmt: MatchType) => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr_1fr] gap-3 rounded-2xl bg-white p-4 shadow-card">
      <PlayerSelect
        label="Player 1"
        value={player1Id}
        onChange={onPlayer1Change}
        players={players}
        loading={playersLoading}
        excludeId={player2Id}
      />
      <div className="flex items-center justify-center">
        <ArrowRightLeft className="h-5 w-5 text-pk-700" aria-hidden />
      </div>
      <PlayerSelect
        label="Player 2"
        value={player2Id}
        onChange={onPlayer2Change}
        players={players}
        loading={playersLoading}
        excludeId={player1Id}
      />
      <FormatSelect value={format} onChange={onFormatChange} />
    </div>
  );
}

function PlayerSelect({
  label,
  value,
  onChange,
  players,
  loading,
  excludeId,
}: {
  label: string;
  value: number | null;
  onChange: (id: number | null) => void;
  players: { id: number; name: string; country: string | null }[];
  loading: boolean;
  excludeId: number | null;
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

function FormatSelect({
  value,
  onChange,
}: {
  value: MatchType | null;
  onChange: (fmt: MatchType) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium uppercase tracking-wider text-ink-500">
        Format
      </label>
      <select
        className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 focus:border-pk-600 focus:outline-none focus:ring-1 focus:ring-pk-600"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value as MatchType)}
      >
        <option value={MatchType.T20I}>T20I</option>
        <option value={MatchType.ODI}>ODI</option>
        <option value={MatchType.TEST}>Test</option>
        <option value={MatchType.T20}>T20 (franchise)</option>
      </select>
    </div>
  );
}

// --------------------------------------------------------------------

function Body({
  playersEmpty,
  loading,
  error,
  data,
  hasSelection,
}: {
  playersEmpty: boolean;
  loading: boolean;
  error: unknown;
  data: ReturnType<typeof useCompare>["data"];
  hasSelection: boolean;
}) {
  if (playersEmpty) {
    return (
      <EmptyState
        title="No players in the database yet"
        icon={<Users className="h-6 w-6 text-pk-700" aria-hidden />}
      />
    );
  }
  if (!hasSelection) {
    return (
      <div className="rounded-2xl bg-white p-10 text-center shadow-card">
        <Users className="mx-auto h-8 w-8 text-pk-700" aria-hidden />
        <h3 className="mt-3 text-lg font-semibold text-ink-900">
          Pick two players and a format
        </h3>
        <p className="mt-1 text-sm text-ink-600">
          Choose any two players from the seeded roster and a match format
          to see the side-by-side comparison.
        </p>
      </div>
    );
  }
  if (loading) {
    // Content-shaped skeletons — same dimensions and rough layout as
    // the resolved view so when data lands there is zero reflow.
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4">
          <ProfileCardSkeleton />
          <ProfileCardSkeleton />
        </div>
        <RadarSkeleton />
        <StatTableSkeleton rows={7} />
        <div className="grid grid-cols-2 gap-4">
          <SparklineSkeleton />
          <SparklineSkeleton />
        </div>
      </div>
    );
  }
  if (error != null) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        Couldn't load comparison —{" "}
        {error instanceof Error ? error.message : "unknown error"}
      </div>
    );
  }
  if (data == null) return null;

  const radarMode = decideRadarMode(data.player1, data.player2);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <PlayerProfileCard profile={data.player1.profile} accent="primary" />
        <PlayerProfileCard profile={data.player2.profile} accent="primary" />
      </div>

      <DataQualityNotice warnings={data.data_quality} />

      {radarMode != null ? (
        <ComparisonRadar
          player1={data.player1}
          player2={data.player2}
          mode={radarMode}
        />
      ) : (
        <div className="rounded-2xl border border-dashed border-ink-200 bg-white p-6 text-sm text-ink-600">
          Players have different primary roles — radar chart needs both to be
          batters or both to be bowlers. Stat tables below show what they
          have in common.
        </div>
      )}

      <StatComparison
        slot1={data.player1}
        slot2={data.player2}
        radarMode={radarMode}
      />

      <div className="grid grid-cols-2 gap-4">
        <FormSparkline
          entries={data.player1.form_guide}
          profile={data.player1.profile}
          accentColor="#01411C"
        />
        <FormSparkline
          entries={data.player2.form_guide}
          profile={data.player2.profile}
          accentColor="#5d966a"
        />
      </div>

      <CommonOpponentsTable data={data} />
    </div>
  );
}

// --------------------------------------------------------------------

function StatComparison({
  slot1,
  slot2,
  radarMode,
}: {
  slot1: PlayerComparisonSlot;
  slot2: PlayerComparisonSlot;
  radarMode: "batting" | "bowling" | null;
}) {
  // Show whichever side(s) both players have data for. If radar is
  // batting → batting stats; bowling → bowling; null (mixed) → both
  // tables stacked.
  const showBatting =
    radarMode === "batting" ||
    (radarMode == null && slot1.batting != null && slot2.batting != null);
  const showBowling =
    radarMode === "bowling" ||
    (radarMode == null && slot1.bowling != null && slot2.bowling != null);

  return (
    <div className="grid gap-4">
      {showBatting && (
        <div className="rounded-2xl bg-white p-6 shadow-card">
          <SectionHeader
            title="Batting career"
            sub="career rollup, scoped to the selected format"
          />
          <div className="grid grid-cols-3 border-b border-ink-200 pb-2 text-xs font-medium uppercase tracking-wider text-ink-500">
            <span>Stat</span>
            <span className="text-right">{slot1.profile.name}</span>
            <span className="text-right">{slot2.profile.name}</span>
          </div>
          <CompareStatRow
            label="Innings"
            player1={slot1.batting?.innings ?? null}
            player2={slot2.batting?.innings ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="Runs"
            player1={slot1.batting?.runs ?? null}
            player2={slot2.batting?.runs ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="Average"
            player1={slot1.batting?.average ?? null}
            player2={slot2.batting?.average ?? null}
            format={(v) => v.toFixed(2)}
          />
          <CompareStatRow
            label="Strike rate"
            player1={slot1.batting?.strike_rate ?? null}
            player2={slot2.batting?.strike_rate ?? null}
            format={(v) => v.toFixed(2)}
          />
          <CompareStatRow
            label="50s"
            player1={slot1.batting?.fifties ?? null}
            player2={slot2.batting?.fifties ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="100s"
            player1={slot1.batting?.hundreds ?? null}
            player2={slot2.batting?.hundreds ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="Highest score"
            player1={slot1.batting?.highest_score ?? null}
            player2={slot2.batting?.highest_score ?? null}
            format={(v) => v.toString()}
          />
        </div>
      )}

      {showBowling && (
        <div className="rounded-2xl bg-white p-6 shadow-card">
          <SectionHeader
            title="Bowling career"
            sub="career rollup, scoped to the selected format"
          />
          <div className="grid grid-cols-3 border-b border-ink-200 pb-2 text-xs font-medium uppercase tracking-wider text-ink-500">
            <span>Stat</span>
            <span className="text-right">{slot1.profile.name}</span>
            <span className="text-right">{slot2.profile.name}</span>
          </div>
          <CompareStatRow
            label="Innings"
            player1={slot1.bowling?.innings ?? null}
            player2={slot2.bowling?.innings ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="Wickets"
            player1={slot1.bowling?.wickets ?? null}
            player2={slot2.bowling?.wickets ?? null}
            format={(v) => v.toString()}
          />
          <CompareStatRow
            label="Average"
            player1={slot1.bowling?.average ?? null}
            player2={slot2.bowling?.average ?? null}
            format={(v) => v.toFixed(2)}
            betterIsLower
          />
          <CompareStatRow
            label="Economy"
            player1={slot1.bowling?.economy ?? null}
            player2={slot2.bowling?.economy ?? null}
            format={(v) => v.toFixed(2)}
            betterIsLower
          />
          <CompareStatRow
            label="5-wicket hauls"
            player1={slot1.bowling?.five_wicket_hauls ?? null}
            player2={slot2.bowling?.five_wicket_hauls ?? null}
            format={(v) => v.toString()}
          />
        </div>
      )}
    </div>
  );
}

function SectionHeader({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="mb-2">
      <h3 className="text-base font-semibold text-ink-900">{title}</h3>
      <p className="text-xs text-ink-500">{sub}</p>
    </div>
  );
}

// --------------------------------------------------------------------

function CommonOpponentsTable({
  data,
}: {
  data: NonNullable<ReturnType<typeof useCompare>["data"]>;
}) {
  const showBatting = data.common_opponents.some(
    (o) =>
      o.player1_batting_average != null || o.player2_batting_average != null
  );
  const showBowling = data.common_opponents.some(
    (o) =>
      o.player1_bowling_wickets != null || o.player2_bowling_wickets != null
  );

  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <SectionHeader
        title="Head-to-head with common opponents"
        sub="opponents both players have faced in the selected format"
      />
      {data.common_opponents.length === 0 ? (
        <p className="rounded-md bg-ink-50 px-3 py-6 text-center text-sm text-ink-500">
          No common opponents in this format yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-200 text-xs font-medium uppercase tracking-wider text-ink-500">
              <tr>
                <th className="py-2 text-left">Opponent</th>
                <th className="py-2 text-right">
                  {data.player1.profile.name}
                  {showBatting && (
                    <div className="text-[10px] font-normal text-ink-400">
                      avg / SR
                    </div>
                  )}
                </th>
                <th className="py-2 text-right">
                  {data.player2.profile.name}
                  {showBatting && (
                    <div className="text-[10px] font-normal text-ink-400">
                      avg / SR
                    </div>
                  )}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.common_opponents.map((row) => (
                <tr
                  key={row.opponent}
                  className="border-b border-ink-100 last:border-b-0"
                >
                  <td className="py-3 font-medium text-ink-800">
                    {row.opponent}
                  </td>
                  <td className="py-3 text-right tabular-nums text-ink-700">
                    {showBatting && (
                      <div>
                        {fmtOrDash(row.player1_batting_average, 2)} /{" "}
                        {fmtOrDash(row.player1_batting_strike_rate, 2)}
                      </div>
                    )}
                    {showBowling && (
                      <div className="text-xs text-ink-500">
                        {fmtOrDash(row.player1_bowling_wickets, 0)} wkts ·{" "}
                        eco {fmtOrDash(row.player1_bowling_economy, 2)}
                      </div>
                    )}
                  </td>
                  <td className="py-3 text-right tabular-nums text-ink-700">
                    {showBatting && (
                      <div>
                        {fmtOrDash(row.player2_batting_average, 2)} /{" "}
                        {fmtOrDash(row.player2_batting_strike_rate, 2)}
                      </div>
                    )}
                    {showBowling && (
                      <div className="text-xs text-ink-500">
                        {fmtOrDash(row.player2_bowling_wickets, 0)} wkts ·{" "}
                        eco {fmtOrDash(row.player2_bowling_economy, 2)}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------

function decideRadarMode(
  p1: PlayerComparisonSlot,
  p2: PlayerComparisonSlot
): "batting" | "bowling" | null {
  const battingBoth = p1.batting != null && p2.batting != null;
  const bowlingBoth = p1.bowling != null && p2.bowling != null;
  // Prefer batting when both qualify — most users compare batters and
  // it's the more recognisable chart shape.
  if (battingBoth) return "batting";
  if (bowlingBoth) return "bowling";
  return null;
}

function parseIntOrNull(raw: string | null): number | null {
  if (raw == null) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

function fmtOrDash(v: number | null | undefined, digits: number): string {
  if (v == null) return "—";
  return digits === 0 ? v.toString() : v.toFixed(digits);
}
