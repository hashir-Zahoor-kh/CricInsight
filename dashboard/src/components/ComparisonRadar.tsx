import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type {
  BattingCareerStats,
  BowlingCareerStats,
  PlayerComparisonSlot,
} from "../api/types";

/**
 * Hero radar chart for the comparison page. Builds a 5-axis profile
 * normalised to [0, 100] so two players' radar shapes are directly
 * comparable regardless of absolute scale.
 *
 * Two modes:
 *   - "batting" picks five batting dimensions:
 *       avg / strike-rate / boundary share /
 *       50+-conversion / hundreds-per-match
 *   - "bowling" picks five bowling dimensions:
 *       wickets / economy (inverted) / 5-wicket-hauls /
 *       average (inverted) / strike-rate (inverted)
 *
 * Inverted dimensions: lower-is-better stats (economy, average) are
 * mirrored so a longer radar arm always means "better player",
 * preserving the visual intuition of the chart.
 */
type Mode = "batting" | "bowling";

const COLOUR_P1 = "#01411C"; // pk-900 — flagship green
const COLOUR_P2 = "#5d966a"; // pk-400 — secondary, distinct but harmonious

export function ComparisonRadar({
  player1,
  player2,
  mode,
}: {
  player1: PlayerComparisonSlot;
  player2: PlayerComparisonSlot;
  mode: Mode;
}) {
  const data =
    mode === "batting"
      ? buildBattingAxes(player1.batting, player2.batting)
      : buildBowlingAxes(player1.bowling, player2.bowling);

  const p1Name = player1.profile.name;
  const p2Name = player2.profile.name;

  return (
    <div className="rounded-2xl bg-white p-6 shadow-card">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-lg font-semibold text-ink-900">
          {mode === "batting" ? "Batting profile" : "Bowling profile"}
        </h3>
        <span className="text-xs text-ink-500">all metrics scaled 0–100</span>
      </div>
      <ResponsiveContainer width="100%" height={360}>
        <RadarChart data={data} outerRadius="78%">
          <PolarGrid stroke="#d4d8dc" />
          <PolarAngleAxis
            dataKey="dim"
            tick={{ fill: "#3f4750", fontSize: 12 }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={{ fill: "#aab1b8", fontSize: 10 }}
            tickCount={5}
          />
          <Radar
            name={p1Name}
            dataKey="player1"
            stroke={COLOUR_P1}
            fill={COLOUR_P1}
            fillOpacity={0.35}
            strokeWidth={2}
          />
          <Radar
            name={p2Name}
            dataKey="player2"
            stroke={COLOUR_P2}
            fill={COLOUR_P2}
            fillOpacity={0.25}
            strokeWidth={2}
          />
          <Tooltip
            formatter={(v) =>
              typeof v === "number" ? `${v.toFixed(1)} / 100` : `${v ?? "—"}`
            }
            contentStyle={{
              borderRadius: 8,
              border: "1px solid #d4d8dc",
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// --------------------------------------------------------------- helpers

function clamp(v: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, v));
}

/** Normalise a value into [0, 100] given a soft cap. */
function normalise(value: number | null | undefined, cap: number): number {
  if (value == null || cap <= 0) return 0;
  return clamp((value / cap) * 100);
}

/** Inverse normalise — used for lower-is-better stats so the chart
 *  preserves the "longer arm = better player" intuition. */
function invertNormalise(
  value: number | null | undefined,
  worst: number
): number {
  if (value == null || worst <= 0) return 0;
  return clamp(((worst - value) / worst) * 100);
}

function buildBattingAxes(
  p1: BattingCareerStats | null,
  p2: BattingCareerStats | null
) {
  // Soft caps reflect realistic top-end values across formats so the
  // axis spans don't crush mid-tier players into the centre.
  const AVG_CAP = 60;
  const SR_CAP_T20 = 180;
  const SR_CAP = 180; // we use the same cap across formats — keeps charts comparable on a single page
  const BOUNDARY_CAP = 0.8; // (4s+6s)/runs — top ODI strikers ~0.7
  const FIFTY_PER_INN_CAP = 0.4;
  const HUNDRED_PER_INN_CAP = 0.15;

  function row(label: string, p1v: number, p2v: number) {
    return { dim: label, player1: p1v, player2: p2v };
  }

  const battingShare = (s: BattingCareerStats | null) =>
    s == null || s.runs === 0 ? 0 : (s.fours * 4 + s.sixes * 6) / s.runs;
  const fiftyShare = (s: BattingCareerStats | null) =>
    s == null || s.innings === 0 ? 0 : s.fifties / s.innings;
  const hundredShare = (s: BattingCareerStats | null) =>
    s == null || s.innings === 0 ? 0 : s.hundreds / s.innings;

  return [
    row(
      "Average",
      normalise(p1?.average ?? null, AVG_CAP),
      normalise(p2?.average ?? null, AVG_CAP)
    ),
    row(
      "Strike rate",
      normalise(p1?.strike_rate ?? null, SR_CAP),
      normalise(p2?.strike_rate ?? null, SR_CAP_T20)
    ),
    row(
      "Boundary %",
      normalise(battingShare(p1), BOUNDARY_CAP),
      normalise(battingShare(p2), BOUNDARY_CAP)
    ),
    row(
      "50s/inn",
      normalise(fiftyShare(p1), FIFTY_PER_INN_CAP),
      normalise(fiftyShare(p2), FIFTY_PER_INN_CAP)
    ),
    row(
      "100s/inn",
      normalise(hundredShare(p1), HUNDRED_PER_INN_CAP),
      normalise(hundredShare(p2), HUNDRED_PER_INN_CAP)
    ),
  ];
}

function buildBowlingAxes(
  p1: BowlingCareerStats | null,
  p2: BowlingCareerStats | null
) {
  const WICKETS_PER_M_CAP = 4; // five-wicket hauls aside, 3-4 is elite
  const ECON_WORST = 12;
  const AVG_WORST = 60;
  const SR_WORST = 80; // bowling SR — balls per wicket
  const FIVE_FER_PER_M_CAP = 0.15;

  function row(label: string, p1v: number, p2v: number) {
    return { dim: label, player1: p1v, player2: p2v };
  }
  const wpm = (s: BowlingCareerStats | null) =>
    s == null || s.matches === 0 ? 0 : s.wickets / s.matches;
  const fiveFerPerMatch = (s: BowlingCareerStats | null) =>
    s == null || s.matches === 0 ? 0 : s.five_wicket_hauls / s.matches;

  return [
    row(
      "Wickets/match",
      normalise(wpm(p1), WICKETS_PER_M_CAP),
      normalise(wpm(p2), WICKETS_PER_M_CAP)
    ),
    row(
      "Economy",
      invertNormalise(p1?.economy ?? null, ECON_WORST),
      invertNormalise(p2?.economy ?? null, ECON_WORST)
    ),
    row(
      "Average",
      invertNormalise(p1?.average ?? null, AVG_WORST),
      invertNormalise(p2?.average ?? null, AVG_WORST)
    ),
    row(
      "Strike rate",
      invertNormalise(p1?.bowling_strike_rate ?? null, SR_WORST),
      invertNormalise(p2?.bowling_strike_rate ?? null, SR_WORST)
    ),
    row(
      "5-fers/match",
      normalise(fiveFerPerMatch(p1), FIVE_FER_PER_M_CAP),
      normalise(fiveFerPerMatch(p2), FIVE_FER_PER_M_CAP)
    ),
  ];
}
