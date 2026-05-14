import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { DataQualityNotice } from "../components/DataQualityNotice";
import { EmptyState } from "../components/EmptyState";
import { FormSparkline } from "../components/FormSparkline";
import {
  KeyStatSkeleton,
  ProfileCardSkeleton,
  Skeleton,
  SparklineSkeleton,
  StatTableSkeleton,
} from "../components/LoadingSkeleton";
import { PlayerProfileCard } from "../components/PlayerProfileCard";
import { usePlayer, usePlayerAverage, usePlayerForm } from "../hooks/useApi";
import type {
  BattingCareerStats,
  BowlingCareerStats,
  FormatBreakdown,
  FormGuideEntry,
  PlayerProfileCard as ProfileCardType,
} from "../api/types";
import { MatchType } from "../api/types";

/**
 * Single-player deep-dive — dark PSL broadcast aesthetic.
 *
 * Sections (top to bottom):
 *   - Back link + player name (Bebas Neue 64px)
 *   - ProfileCard (identity, role badge)
 *   - Format pills (T20I / ODI / Test / T20 franchise)
 *   - HeroStat — ONE neon-lime 64px number for selected format
 *   - By-format career table — JetBrains Mono, no second accent colour
 *   - Form sparkline (last 10 innings, animated pathLength)
 */
export function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const playerId = id != null ? Number.parseInt(id, 10) : null;
  const [fmt, setFmt] = useState<MatchType>(MatchType.T20I);

  const playerQuery = usePlayer(playerId);
  const averageQuery = usePlayerAverage(playerId);
  const formQuery = usePlayerForm(playerId, fmt);

  if (playerQuery.isLoading) {
    return (
      <div className="mx-auto w-full max-w-[1440px] space-y-6 px-12 py-10">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-14 w-80" />
        <ProfileCardSkeleton />
        <div className="flex gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-8 w-16" />
          ))}
        </div>
        <KeyStatSkeleton />
        <StatTableSkeleton rows={4} />
        <SparklineSkeleton />
      </div>
    );
  }

  if (playerQuery.isError || playerQuery.data == null) {
    return (
      <EmptyState
        title="Player not found"
        description={
          <Link to="/" className="text-accent underline">
            Back to home
          </Link>
        }
      />
    );
  }

  const player = playerQuery.data;
  const profile: ProfileCardType = averageQuery.data?.profile ?? {
    id: player.id,
    external_id: player.external_id,
    name: player.name,
    country: player.country,
    role: player.role,
    primary_role: player.role ?? "batsman",
    batting_style: player.batting_style,
    bowling_style: player.bowling_style,
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 px-12 py-10">
      {/* Back + heading */}
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1 font-sans text-[11px] uppercase tracking-widest text-fg-secondary transition-colors hover:text-accent"
        >
          <ArrowLeft className="h-3 w-3" aria-hidden /> Home
        </Link>
        <h1 className="mt-4 font-display text-[64px] uppercase leading-none tracking-tight text-fg">
          {player.name}
        </h1>
      </div>

      <PlayerProfileCard profile={profile} />

      {averageQuery.data && (
        <DataQualityNotice warnings={averageQuery.data.data_quality} />
      )}

      <FormatPills value={fmt} onChange={setFmt} />

      <HeroStat
        loading={averageQuery.isLoading}
        breakdowns={averageQuery.data?.by_format ?? []}
        fmt={fmt}
      />

      <ByFormatTable
        loading={averageQuery.isLoading}
        breakdowns={averageQuery.data?.by_format ?? []}
      />

      <FormSection
        loading={formQuery.isLoading}
        entries={formQuery.data?.innings ?? []}
        profile={profile}
      />
    </div>
  );
}

// ====================================================================
// Format pills — border-based, matches ComparisonPage style
// ====================================================================

function FormatPills({
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
    { value: MatchType.T20, label: "T20 franchise" },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={`border px-3 py-1.5 font-sans text-xs uppercase tracking-widest transition-colors ${
              active
                ? "border-accent text-accent"
                : "border-line text-fg-muted hover:border-fg-muted hover:text-fg"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ====================================================================
// HeroStat — THE single neon-lime number for the selected format
// ====================================================================

function HeroStat({
  loading,
  breakdowns,
  fmt,
}: {
  loading: boolean;
  breakdowns: FormatBreakdown[];
  fmt: MatchType;
}) {
  if (loading) return <KeyStatSkeleton />;

  const row = breakdowns.find((b) => b.format === fmt);
  const hasBatting = row?.batting != null;
  const value = hasBatting
    ? row!.batting!.average
    : (row?.bowling?.wickets ?? null);
  const label = hasBatting ? "Batting avg" : row?.bowling ? "Wickets" : "Stat";
  const formatted =
    value == null
      ? "—"
      : hasBatting
        ? value.toFixed(2)
        : value.toString();

  return (
    <div className="flex min-h-[160px] flex-col justify-between border border-line bg-surface p-6 transition-colors duration-150 hover:border-[#333333]">
      <div className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
        {label} · {fmt}
      </div>
      <div className="font-mono text-[64px] leading-none tabular-nums text-accent">
        {formatted}
      </div>
    </div>
  );
}

// ====================================================================
// By-format career table
// ====================================================================

function ByFormatTable({
  loading,
  breakdowns,
}: {
  loading: boolean;
  breakdowns: FormatBreakdown[];
}) {
  if (loading) return <StatTableSkeleton rows={4} />;

  if (breakdowns.length === 0) {
    return (
      <div className="border border-line bg-surface p-6">
        <h3 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Career averages by format
        </h3>
        <p className="mt-6 text-center font-mono text-[11px] uppercase tracking-widest text-fg-muted">
          No stats yet — run the seed script.
        </p>
      </div>
    );
  }

  return (
    <div className="border border-line bg-surface transition-colors duration-150 hover:border-[#333333]">
      <div className="border-b border-line p-6">
        <h3 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Career averages by format
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-line">
              {["Format", "Inn", "Runs", "Avg", "SR", "Wkts", "Eco"].map(
                (h, i) => (
                  <th
                    key={h}
                    className={`px-6 py-3 font-sans text-[10px] uppercase tracking-widest text-fg-secondary ${
                      i === 0 ? "text-left" : "text-right"
                    }`}
                  >
                    {h}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody>
            {breakdowns.map((row, i) => (
              <FormatRow
                key={row.format}
                row={row}
                zebra={i % 2 === 0 ? "surface" : "canvas"}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FormatRow({
  row,
  zebra,
}: {
  row: FormatBreakdown;
  zebra: "surface" | "canvas";
}) {
  const bat: BattingCareerStats | null = row.batting;
  const bowl: BowlingCareerStats | null = row.bowling;
  const bg = zebra === "surface" ? "bg-surface" : "bg-canvas";

  return (
    <tr
      className={`border-b border-line/60 last:border-b-0 ${bg} font-mono text-sm`}
    >
      <td className="px-6 py-3 font-sans text-sm text-fg">{row.format}</td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bat?.innings ?? bowl?.innings ?? "—"}
      </td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bat?.runs ?? "—"}
      </td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bat?.average != null ? bat.average.toFixed(2) : "—"}
      </td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bat?.strike_rate != null ? bat.strike_rate.toFixed(2) : "—"}
      </td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bowl?.wickets ?? "—"}
      </td>
      <td className="px-6 py-3 text-right tabular-nums text-fg">
        {bowl?.economy != null ? bowl.economy.toFixed(2) : "—"}
      </td>
    </tr>
  );
}

// ====================================================================
// Form sparkline section
// ====================================================================

function FormSection({
  loading,
  entries,
  profile,
}: {
  loading: boolean;
  entries: FormGuideEntry[];
  profile: ProfileCardType;
}) {
  if (loading) return <SparklineSkeleton />;
  return (
    <FormSparkline
      entries={entries}
      profile={profile}
      accentColor="#CCFF00"
      delay={0}
    />
  );
}
