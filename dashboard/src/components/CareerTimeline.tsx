import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PlayerRole, TimelineResponse } from "../api/types";

const ACCENT = "#CCFF00";
const GRID = "#222222";
const TICK = "#555555";
const LINE = "#888888";

export function CareerTimeline({
  data,
  primaryRole,
}: {
  data: TimelineResponse;
  primaryRole: PlayerRole;
}) {
  const { years } = data;

  if (years.length === 0) {
    return (
      <div className="border border-line bg-surface p-6">
        <h3 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Career Timeline
        </h3>
        <p className="mt-6 text-center font-mono text-[11px] uppercase tracking-widest text-fg-muted">
          No timeline data in this format.
        </p>
      </div>
    );
  }

  const isBowler = primaryRole === "bowler";
  const volumeKey = isBowler ? "wickets" : "runs";
  const rateKey = isBowler ? "bowling_economy" : "batting_average";
  const volumeLabel = isBowler ? "Wickets" : "Runs";
  const rateLabel = isBowler ? "Economy" : "Average";

  return (
    <div className="border border-line bg-surface transition-colors duration-150 hover:border-[#333333]">
      <div className="border-b border-line p-6">
        <h3 className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
          Career Timeline · {data.format}
        </h3>
      </div>

      <div className="p-6">
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart
            data={years}
            margin={{ top: 4, right: 44, left: 0, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={GRID}
              vertical={false}
            />
            <XAxis
              dataKey="year"
              tick={{ fill: TICK, fontSize: 10, fontFamily: "var(--font-mono)" }}
              axisLine={{ stroke: GRID }}
              tickLine={false}
            />
            <YAxis
              yAxisId="vol"
              orientation="left"
              tick={{ fill: TICK, fontSize: 10, fontFamily: "var(--font-mono)" }}
              axisLine={false}
              tickLine={false}
              width={36}
            />
            <YAxis
              yAxisId="rate"
              orientation="right"
              tick={{ fill: TICK, fontSize: 10, fontFamily: "var(--font-mono)" }}
              axisLine={false}
              tickLine={false}
              width={36}
            />
            <Tooltip
              content={<ChartTooltip rateLabel={rateLabel} />}
              cursor={{ fill: "#1a1a1a" }}
            />
            <Bar
              yAxisId="vol"
              dataKey={volumeKey}
              name={volumeLabel}
              fill={ACCENT}
              fillOpacity={0.85}
              maxBarSize={36}
            />
            <Line
              yAxisId="rate"
              type="monotone"
              dataKey={rateKey}
              name={rateLabel}
              stroke={LINE}
              strokeWidth={1.5}
              dot={{ fill: LINE, r: 2.5, strokeWidth: 0 }}
              activeDot={{ fill: ACCENT, r: 4, strokeWidth: 0 }}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>

        {/* Legend */}
        <div className="mt-3 flex justify-end gap-6">
          <div className="flex items-center gap-1.5">
            <span
              className="block h-2.5 w-2.5"
              style={{ background: ACCENT, opacity: 0.85 }}
            />
            <span className="font-mono text-[10px] uppercase tracking-widest text-fg-muted">
              {volumeLabel}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="block h-0.5 w-4" style={{ background: LINE }} />
            <span className="font-mono text-[10px] uppercase tracking-widest text-fg-muted">
              {rateLabel}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------

function ChartTooltip({
  active,
  payload,
  label,
  rateLabel,
}: {
  active?: boolean;
  payload?: { name: string; value: number | null; fill?: string; stroke?: string }[];
  label?: number;
  rateLabel: string;
}) {
  if (!active || !payload?.length) return null;

  const fmt = (name: string, val: number | null) => {
    if (val == null) return "—";
    return name === rateLabel ? val.toFixed(2) : String(val);
  };

  return (
    <div className="border border-line bg-elevated px-3 py-2">
      <p className="mb-1.5 font-sans text-[10px] uppercase tracking-widest text-fg-secondary">
        {label}
      </p>
      {payload.map((p) => (
        <p
          key={p.name}
          className="font-mono text-[11px] tabular-nums"
          style={{ color: p.fill ?? p.stroke ?? "#ccc" }}
        >
          {p.name}: {fmt(p.name, p.value)}
        </p>
      ))}
    </div>
  );
}
