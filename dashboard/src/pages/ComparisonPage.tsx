import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { ComparisonRadar } from "../components/ComparisonRadar";
import { DataQualityNotice } from "../components/DataQualityNotice";
import { FormSparkline } from "../components/FormSparkline";
import {
  KeyStatSkeleton,
  OpponentsTableSkeleton,
  ProfileCardSkeleton,
  RadarSkeleton,
  SparklineSkeleton,
} from "../components/LoadingSkeleton";
import { PlayerProfileCard } from "../components/PlayerProfileCard";
import { PlayerSearchPicker } from "../components/PlayerSearchPicker";
import { useCompare } from "../hooks/useApi";
import {
  MatchType,
  type CommonOpponentBlock,
  type ComparisonResponse,
  type PlayerComparisonSlot,
} from "../api/types";

/**
 * THE flagship page — Visual Redesign Bento Grid.
 *
 * URL state (`p1`, `p2`, `fmt`) drives the layout so links remain
 * shareable. A thin pickers row at the top lets the user swap either
 * slot in-page without going back to /. Below that, four content
 * rows:
 *
 *   Row 1 — two profile header cards (full-width grid)
 *   Row 2 — narrow key-stat │ wide radar │ narrow key-stat
 *   Row 3 — two animated form sparklines (P1: lime, P2: green)
 *   Row 4 — common-opponents table, dense monospace
 */
export function ComparisonPage() {
  const [params, setParams] = useSearchParams();

  const player1Id = parseIntOrNull(params.get("p1"));
  const player2Id = parseIntOrNull(params.get("p2"));
  const formatParam = (params.get("fmt") as MatchType | null) ?? null;

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

  const hasSelection =
    player1Id != null && player2Id != null && formatParam != null;

  return (
    <div className="mx-auto w-full max-w-[1440px] px-12 py-10">
      <PickersRow
        player1Id={player1Id}
        player2Id={player2Id}
        format={formatParam}
        onPlayer1Change={(id) =>
          updateParam("p1", id == null ? null : String(id))
        }
        onPlayer2Change={(id) =>
          updateParam("p2", id == null ? null : String(id))
        }
        onFormatChange={(fmt) => updateParam("fmt", fmt)}
      />

      <div className="mt-8">
        <Body
          loading={compareQuery.isLoading || compareQuery.isFetching}
          error={compareQuery.error}
          data={compareQuery.data}
          hasSelection={hasSelection}
        />
      </div>
    </div>
  );
}

// ====================================================================
// Pickers row
// ====================================================================

function PickersRow({
  player1Id,
  player2Id,
  format,
  onPlayer1Change,
  onPlayer2Change,
  onFormatChange,
}: {
  player1Id: number | null;
  player2Id: number | null;
  format: MatchType | null;
  onPlayer1Change: (id: number | null) => void;
  onPlayer2Change: (id: number | null) => void;
  onFormatChange: (fmt: MatchType) => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-6 border border-line bg-surface p-5">
      <PlayerSearchPicker
        label="Player 1"
        value={player1Id}
        onChange={onPlayer1Change}
        excludeId={player2Id}
      />
      <PlayerSearchPicker
        label="Player 2"
        value={player2Id}
        onChange={onPlayer2Change}
        excludeId={player1Id}
      />
      <FormatPills value={format} onChange={onFormatChange} />
    </div>
  );
}

function FormatPills({
  value,
  onChange,
}: {
  value: MatchType | null;
  onChange: (fmt: MatchType) => void;
}) {
  const options: { value: MatchType; label: string }[] = [
    { value: MatchType.T20I, label: "T20I" },
    { value: MatchType.ODI, label: "ODI" },
    { value: MatchType.TEST, label: "Test" },
  ];
  return (
    <div>
      <div className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
        Format
      </div>
      <div className="mt-2 flex gap-2">
        {options.map((o) => {
          const isSelected = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(o.value)}
              className={`border px-3 py-1.5 font-sans text-xs uppercase tracking-widest transition-colors ${
                isSelected
                  ? "border-accent text-accent"
                  : "border-line text-fg-muted hover:border-fg-muted hover:text-fg"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ====================================================================
// Body — empty / loading / error / resolved
// ====================================================================

function Body({
  loading,
  error,
  data,
  hasSelection,
}: {
  loading: boolean;
  error: unknown;
  data: ComparisonResponse | undefined;
  hasSelection: boolean;
}) {
  if (!hasSelection) {
    return (
      <div className="border border-line bg-surface px-10 py-16 text-center">
        <p className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Awaiting selection
        </p>
        <h3 className="mt-3 font-display text-3xl uppercase tracking-tight text-fg">
          Pick two players and a format
        </h3>
        <p className="mx-auto mt-3 max-w-md font-sans text-sm text-fg-muted">
          Choose any two players from the seeded roster and a match format
          to see the side-by-side comparison.
        </p>
      </div>
    );
  }
  if (loading) {
    return <BentoSkeleton />;
  }
  if (error != null) {
    return (
      <div className="border border-red-500/50 bg-red-500/[0.05] p-6 font-sans text-sm text-red-300">
        <p className="font-mono text-[11px] uppercase tracking-widest text-red-300">
          Couldn't load comparison
        </p>
        <p className="mt-2 text-red-200/80">
          {error instanceof Error ? error.message : "unknown error"}
        </p>
      </div>
    );
  }
  if (data == null) return null;

  return <BentoGrid data={data} />;
}

// ====================================================================
// Bento Grid
// ====================================================================

function BentoGrid({ data }: { data: ComparisonResponse }) {
  const radarMode = decideRadarMode(data.player1, data.player2);
  return (
    <div className="space-y-6">
      <DataQualityNotice warnings={data.data_quality} />

      {/* ----------------------------- Row 1 — player headers */}
      <div className="grid grid-cols-2 gap-6">
        <PlayerProfileCard profile={data.player1.profile} />
        <PlayerProfileCard profile={data.player2.profile} />
      </div>

      {/* ----------------------------- Row 2 — stat / radar / stat */}
      <div className="grid grid-cols-[1fr_3fr_1fr] gap-6">
        <KeyStatCard slot={data.player1} mode={radarMode} />
        {radarMode != null ? (
          <ComparisonRadar
            player1={data.player1}
            player2={data.player2}
            mode={radarMode}
          />
        ) : (
          <MixedRoleNotice />
        )}
        <KeyStatCard slot={data.player2} mode={radarMode} />
      </div>

      {/* ----------------------------- Row 3 — form sparklines */}
      <div className="grid grid-cols-2 gap-6">
        <FormSparkline
          entries={data.player1.form_guide}
          profile={data.player1.profile}
          accentColor="#CCFF00"
          delay={0}
        />
        <FormSparkline
          entries={data.player2.form_guide}
          profile={data.player2.profile}
          accentColor="#004225"
          delay={0.3}
        />
      </div>

      {/* ----------------------------- Row 4 — common opponents */}
      <CommonOpponentsTable data={data} />
    </div>
  );
}

function BentoSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-6">
        <ProfileCardSkeleton />
        <ProfileCardSkeleton />
      </div>
      <div className="grid grid-cols-[1fr_3fr_1fr] gap-6">
        <KeyStatSkeleton />
        <RadarSkeleton />
        <KeyStatSkeleton />
      </div>
      <div className="grid grid-cols-2 gap-6">
        <SparklineSkeleton />
        <SparklineSkeleton />
      </div>
      <OpponentsTableSkeleton rows={4} />
    </div>
  );
}

// ====================================================================
// Row 2 — narrow key-stat card (the single neon-lime number per slot)
// ====================================================================

function KeyStatCard({
  slot,
  mode,
}: {
  slot: PlayerComparisonSlot;
  mode: "batting" | "bowling" | null;
}) {
  // Pick the headline number consistent with the radar mode. When
  // roles are mixed (radar disabled) fall back to whichever side the
  // player actually has data for; that keeps the card meaningful even
  // when the centrepiece chart can't render.
  const effective: "batting" | "bowling" =
    mode ??
    (slot.batting != null
      ? "batting"
      : slot.bowling != null
        ? "bowling"
        : "batting");

  let headline: string = "—";
  let label: string = "Average";

  if (effective === "batting") {
    label = "Batting average";
    if (slot.batting?.average != null) {
      headline = slot.batting.average.toFixed(2);
    }
  } else {
    label = "Wickets";
    if (slot.bowling != null) {
      headline = slot.bowling.wickets.toString();
    }
  }

  return (
    <div className="flex min-h-[260px] flex-col justify-between border border-line bg-surface p-6">
      <div className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
        {label}
      </div>
      <div className="font-mono text-[64px] leading-none tabular-nums text-accent">
        {headline}
      </div>
      <div className="truncate font-sans text-[11px] uppercase tracking-widest text-fg-muted">
        {slot.profile.name}
      </div>
    </div>
  );
}

function MixedRoleNotice() {
  return (
    <div className="flex items-center justify-center border border-dashed border-line bg-surface px-6 py-8 text-center">
      <p className="font-sans text-sm text-fg-secondary">
        Different primary roles — radar needs both players to share a
        discipline. Common-opponents table below still applies.
      </p>
    </div>
  );
}

// ====================================================================
// Row 4 — common opponents table
// ====================================================================

function CommonOpponentsTable({ data }: { data: ComparisonResponse }) {
  const opponents = data.common_opponents;

  const battingMode = opponents.some(
    (o) =>
      o.player1_batting_average != null || o.player2_batting_average != null
  );
  const bowlingMode = !battingMode &&
    opponents.some(
      (o) =>
        o.player1_bowling_wickets != null || o.player2_bowling_wickets != null
    );

  return (
    <div className="border border-line bg-surface">
      <div className="border-b border-line p-6">
        <h3 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Head-to-head · common opponents
        </h3>
        <p className="mt-1 font-sans text-xs text-fg-muted">
          Opponents both players have faced in the selected format.
        </p>
      </div>

      {opponents.length === 0 ? (
        <p className="px-6 py-10 text-center font-mono text-[11px] uppercase tracking-widest text-fg-muted">
          No common opponents in this format yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="px-6 py-3 text-left font-sans text-[10px] uppercase tracking-widest text-fg-secondary">
                  Opponent
                </th>
                <th className="px-6 py-3 text-right font-sans text-[10px] uppercase tracking-widest text-fg-secondary">
                  {data.player1.profile.name}
                  <div className="font-mono text-[10px] normal-case tracking-normal text-fg-muted">
                    {battingMode ? "avg · sr" : "wkts · eco"}
                  </div>
                </th>
                <th className="px-6 py-3 text-right font-sans text-[10px] uppercase tracking-widest text-fg-secondary">
                  {data.player2.profile.name}
                  <div className="font-mono text-[10px] normal-case tracking-normal text-fg-muted">
                    {battingMode ? "avg · sr" : "wkts · eco"}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {opponents.map((row, i) => (
                <OpponentRow
                  key={row.opponent}
                  row={row}
                  zebra={i % 2 === 0 ? "surface" : "canvas"}
                  battingMode={battingMode}
                  bowlingMode={bowlingMode}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function OpponentRow({
  row,
  zebra,
  battingMode,
  bowlingMode,
}: {
  row: CommonOpponentBlock;
  zebra: "surface" | "canvas";
  battingMode: boolean;
  bowlingMode: boolean;
}) {
  // Spec: "neon lime for better value" — per row, whoever has the
  // better headline metric (avg / wickets) is highlighted. Ties leave
  // both sides neutral so the accent stays meaningful.
  let p1Better = false;
  let p2Better = false;
  if (battingMode) {
    const a = row.player1_batting_average;
    const b = row.player2_batting_average;
    if (a != null && b != null && a !== b) {
      p1Better = a > b;
      p2Better = b > a;
    }
  } else if (bowlingMode) {
    const a = row.player1_bowling_wickets;
    const b = row.player2_bowling_wickets;
    if (a != null && b != null && a !== b) {
      p1Better = a > b;
      p2Better = b > a;
    }
  }

  const bg = zebra === "surface" ? "bg-surface" : "bg-canvas";

  return (
    <tr className={`border-b border-line/60 last:border-b-0 ${bg}`}>
      <td className="px-6 py-3 font-sans text-sm text-fg">{row.opponent}</td>
      <td className="px-6 py-3 text-right">
        {battingMode ? (
          <CellBatting
            avg={row.player1_batting_average}
            sr={row.player1_batting_strike_rate}
            highlight={p1Better}
          />
        ) : (
          <CellBowling
            wkts={row.player1_bowling_wickets}
            eco={row.player1_bowling_economy}
            highlight={p1Better}
          />
        )}
      </td>
      <td className="px-6 py-3 text-right">
        {battingMode ? (
          <CellBatting
            avg={row.player2_batting_average}
            sr={row.player2_batting_strike_rate}
            highlight={p2Better}
          />
        ) : (
          <CellBowling
            wkts={row.player2_bowling_wickets}
            eco={row.player2_bowling_economy}
            highlight={p2Better}
          />
        )}
      </td>
    </tr>
  );
}

function CellBatting({
  avg,
  sr,
  highlight,
}: {
  avg: number | null;
  sr: number | null;
  highlight: boolean;
}) {
  const top = highlight ? "text-accent" : "text-fg";
  return (
    <div className="tabular-nums">
      <div className={`text-sm ${top}`}>{fmtOrDash(avg, 2)}</div>
      <div className="text-xs text-fg-muted">{fmtOrDash(sr, 2)} sr</div>
    </div>
  );
}

function CellBowling({
  wkts,
  eco,
  highlight,
}: {
  wkts: number | null;
  eco: number | null;
  highlight: boolean;
}) {
  const top = highlight ? "text-accent" : "text-fg";
  return (
    <div className="tabular-nums">
      <div className={`text-sm ${top}`}>{fmtOrDash(wkts, 0)} wkts</div>
      <div className="text-xs text-fg-muted">{fmtOrDash(eco, 2)} eco</div>
    </div>
  );
}

// ====================================================================
// helpers
// ====================================================================

function decideRadarMode(
  p1: PlayerComparisonSlot,
  p2: PlayerComparisonSlot
): "batting" | "bowling" | null {
  const battingBoth = p1.batting != null && p2.batting != null;
  const bowlingBoth = p1.bowling != null && p2.bowling != null;
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
