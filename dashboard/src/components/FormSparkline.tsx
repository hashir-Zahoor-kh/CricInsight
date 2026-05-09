import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { FormGuideEntry, PlayerProfileCard } from "../api/types";

/**
 * Last-10-innings sparkline. Reads the appropriate half of each
 * FormGuideEntry based on the player's primary_role:
 *   - batsman / wicketkeeper / all-rounder → batting_runs
 *   - bowler                               → bowling_wickets
 *
 * The X axis is innings index (most recent on the right) rather than
 * the date — uniform spacing reads cleaner than wall-clock with
 * irregular intervals between matches.
 */
export function FormSparkline({
  entries,
  profile,
  accentColor = "#01411C",
}: {
  entries: FormGuideEntry[];
  profile: PlayerProfileCard;
  accentColor?: string;
}) {
  const useBowling = profile.primary_role === "bowler";

  // Reverse so most-recent innings is on the right of the chart —
  // matches how cricket fans naturally read form (left = older).
  const data = [...entries].reverse().map((e, i) => ({
    idx: i + 1,
    label: useBowling ? "Wickets" : "Runs",
    value: useBowling ? e.bowling_wickets : e.batting_runs,
    opponent: e.opponent,
    matchType: e.match_type,
    date: e.date,
  }));

  const yLabel = useBowling ? "Wickets" : "Runs";

  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink-900">
          Last {entries.length} {useBowling ? "spells" : "innings"} —{" "}
          {profile.name}
        </h3>
        <span className="text-xs text-ink-500">{yLabel}</span>
      </div>
      {entries.length === 0 ? (
        <div className="mt-4 flex h-32 items-center justify-center rounded-md bg-ink-50 text-sm text-ink-500">
          No recent innings in this format.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart
            data={data}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid stroke="#eceef0" vertical={false} />
            <XAxis
              dataKey="idx"
              tick={{ fill: "#7c848d", fontSize: 11 }}
              axisLine={{ stroke: "#d4d8dc" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "#7c848d", fontSize: 11 }}
              axisLine={{ stroke: "#d4d8dc" }}
              tickLine={false}
              width={28}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                border: "1px solid #d4d8dc",
                fontSize: 12,
              }}
              labelFormatter={(idx) => {
                const row = data[Number(idx) - 1];
                if (!row) return "";
                return `vs ${row.opponent} · ${row.matchType}`;
              }}
              formatter={(v) => [v, yLabel]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={accentColor}
              strokeWidth={2}
              dot={{ r: 3, fill: accentColor }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
