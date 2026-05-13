import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { DataQualityNotice } from "../components/DataQualityNotice";
import { EmptyState } from "../components/EmptyState";
import { FormSparkline } from "../components/FormSparkline";
import {
  ProfileCardSkeleton,
  Skeleton,
  SparklineSkeleton,
  StatTableSkeleton,
} from "../components/LoadingSkeleton";
import { PlayerProfileCard } from "../components/PlayerProfileCard";
import {
  usePlayer,
  usePlayerAverage,
  usePlayerForm,
} from "../hooks/useApi";
import { MatchType } from "../api/types";

/**
 * Single-player deep-dive — supporting page for the comparison flow.
 *
 * Sections:
 *   - profile card
 *   - format selector (T20I / ODI / Test / T20)
 *   - by-format career averages (table)
 *   - last-10 form sparkline for selected format
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
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <ProfileCardSkeleton />
        <Skeleton className="h-12" />
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
          <>
            <Link to="/" className="text-pk-700 underline">
              Back to home
            </Link>
          </>
        }
      />
    );
  }

  const player = playerQuery.data;
  const profile = averageQuery.data?.profile ?? {
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
    <div className="space-y-6">
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm text-pk-700 hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Home
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink-900">
          Player Profile
        </h1>
        <p className="text-ink-600">{player.name}</p>
      </div>

      <PlayerProfileCard profile={profile} />

      {averageQuery.data && (
        <DataQualityNotice warnings={averageQuery.data.data_quality} />
      )}

      <FormatTabs value={fmt} onChange={setFmt} />

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

// --------------------------------------------------------------------

function FormatTabs({
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
    <div className="flex gap-1 rounded-xl bg-white p-1 shadow-card">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            o.value === value
              ? "bg-pk-900 text-white"
              : "text-ink-700 hover:bg-ink-50"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ByFormatTable({
  loading,
  breakdowns,
}: {
  loading: boolean;
  breakdowns: { format: string; batting: any; bowling: any }[];
}) {
  if (loading) {
    return <StatTableSkeleton rows={4} />;
  }
  if (breakdowns.length === 0) {
    return (
      <div className="rounded-2xl bg-white p-6 shadow-card">
        <h3 className="text-base font-semibold text-ink-900">
          By-format breakdown
        </h3>
        <p className="mt-3 rounded-md bg-ink-50 px-3 py-6 text-center text-sm text-ink-500">
          No format stats yet — run the seed script to populate.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <h3 className="text-base font-semibold text-ink-900">
        Career averages by format
      </h3>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-ink-200 text-xs font-medium uppercase tracking-wider text-ink-500">
            <tr>
              <th className="py-2 text-left">Format</th>
              <th className="py-2 text-right">Innings</th>
              <th className="py-2 text-right">Runs</th>
              <th className="py-2 text-right">Avg</th>
              <th className="py-2 text-right">SR</th>
              <th className="py-2 text-right">Wkts</th>
              <th className="py-2 text-right">Eco</th>
            </tr>
          </thead>
          <tbody>
            {breakdowns.map((row) => (
              <tr
                key={row.format}
                className="border-b border-ink-100 last:border-b-0"
              >
                <td className="py-3 font-medium text-ink-800">{row.format}</td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.batting?.innings ?? row.bowling?.innings ?? "—"}
                </td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.batting?.runs ?? "—"}
                </td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.batting?.average?.toFixed(2) ?? "—"}
                </td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.batting?.strike_rate?.toFixed(2) ?? "—"}
                </td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.bowling?.wickets ?? "—"}
                </td>
                <td className="py-3 text-right tabular-nums text-ink-700">
                  {row.bowling?.economy?.toFixed(2) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FormSection({
  loading,
  entries,
  profile,
}: {
  loading: boolean;
  entries: import("../api/types").FormGuideEntry[];
  profile: import("../api/types").PlayerProfileCard;
}) {
  if (loading) return <SparklineSkeleton />;
  return (
    <FormSparkline
      entries={entries}
      profile={profile}
      accentColor="#01411C"
    />
  );
}
