/**
 * TypeScript mirrors of every backend Pydantic schema in
 * `backend/app/schemas/`. Field names and nullability match the
 * Pydantic source verbatim — drift between these types and the
 * server response is the kind of bug that hides for weeks.
 *
 * The source-of-truth files on the backend:
 *   - app/schemas/analytics.py   (ComparisonResponse + family)
 *   - app/schemas/player.py      (PlayerResponse, PlayerWithStats)
 *   - app/schemas/match.py       (MatchResponse)
 *   - app/schemas/stats.py       (BattingStatsResponse, BowlingStatsResponse)
 *   - app/models/enums.py        (MatchType, PlayerRole, TossDecision)
 *
 * Conventions used here that mirror Pydantic:
 *   - `string | null` matches Pydantic `Optional[str]` / `str | None`
 *   - Enums emit their `.value` over JSON, so "Test", "ODI", "T20I",
 *     "T20" / "batsman", "bowler", … are the literal wire values.
 *   - Datetimes arrive as ISO 8601 strings (FastAPI's default JSON
 *     encoder); typed as `string` here, components turn them into Date.
 */

// ====================================================================
// Enums — must match Pydantic StrEnum values exactly
// ====================================================================

export const MatchType = {
  TEST: "Test",
  ODI: "ODI",
  T20I: "T20I",
  T20: "T20",
} as const;
export type MatchType = (typeof MatchType)[keyof typeof MatchType];

export const PlayerRole = {
  BATSMAN: "batsman",
  BOWLER: "bowler",
  ALL_ROUNDER: "allrounder",
  WICKETKEEPER: "wicketkeeper",
} as const;
export type PlayerRole = (typeof PlayerRole)[keyof typeof PlayerRole];

export const TossDecision = {
  BAT: "bat",
  BOWL: "bowl",
} as const;
export type TossDecision = (typeof TossDecision)[keyof typeof TossDecision];

// ====================================================================
// analytics.py — flagship comparison shapes
// ====================================================================

/** Mirrors Pydantic `DataQualityWarning`. */
export interface DataQualityWarning {
  code: string;
  message: string;
  affected: string | null;
}

/** Mirrors Pydantic `PlayerProfileCard`. */
export interface PlayerProfileCard {
  id: number;
  external_id: string | null;
  name: string;
  country: string | null;
  role: PlayerRole | null;
  /** Always populated — service layer derives it from declared role
   *  or the batting/bowling innings ratio when role is null. */
  primary_role: PlayerRole;
  batting_style: string | null;
  bowling_style: string | null;
}

/** Mirrors Pydantic `BattingCareerStats`. */
export interface BattingCareerStats {
  matches: number;
  innings: number;
  not_outs: number;
  runs: number;
  /** null when (innings - not_outs) === 0 — average is undefined. */
  average: number | null;
  /** null when balls_faced is unknown / 0. */
  strike_rate: number | null;
  fifties: number;
  hundreds: number;
  highest_score: number;
  fours: number;
  sixes: number;
}

/** Mirrors Pydantic `BowlingCareerStats`. */
export interface BowlingCareerStats {
  matches: number;
  innings: number;
  overs_bowled: number;
  runs_conceded: number;
  wickets: number;
  /** null when wickets === 0 — average is undefined. */
  average: number | null;
  /** null when overs_bowled === 0. */
  economy: number | null;
  /** Bowling SR = balls bowled / wickets. Different from batting SR. */
  bowling_strike_rate: number | null;
  /** Derived: wickets / matches. Null when matches === 0. */
  wickets_per_match: number | null;
  /** Reserved — requires ball-by-ball storage. Always null today. */
  dot_ball_pct: number | null;
  five_wicket_hauls: number;
  best_figures: string | null;
}

/** Mirrors Pydantic `FormGuideEntry`. Both batting and bowling halves
 *  are independently nullable; pure-batter rows have only the batting
 *  half populated, pure-bowler rows have only the bowling half. */
export interface FormGuideEntry {
  match_external_id: string;
  /** ISO 8601 string. */
  date: string;
  opponent: string;
  venue: string | null;
  match_type: MatchType;

  batting_runs: number | null;
  batting_balls: number | null;
  batting_strike_rate: number | null;
  not_out: boolean | null;

  bowling_overs: number | null;
  bowling_wickets: number | null;
  bowling_runs_conceded: number | null;
  bowling_economy: number | null;
}

/** Mirrors Pydantic `CommonOpponentBlock`. */
export interface CommonOpponentBlock {
  opponent: string;
  player1_matches: number;
  player2_matches: number;

  player1_batting_average: number | null;
  player1_batting_strike_rate: number | null;
  player2_batting_average: number | null;
  player2_batting_strike_rate: number | null;

  player1_bowling_wickets: number | null;
  player1_bowling_economy: number | null;
  player2_bowling_wickets: number | null;
  player2_bowling_economy: number | null;
}

/** Mirrors Pydantic `PlayerComparisonSlot`. */
export interface PlayerComparisonSlot {
  profile: PlayerProfileCard;
  /** null when this slot is a pure-bowler with no batting innings. */
  batting: BattingCareerStats | null;
  /** null when this slot is a pure-batter with no bowling innings. */
  bowling: BowlingCareerStats | null;
  /** Capped at 10 by the server (Pydantic max_length=10). */
  form_guide: FormGuideEntry[];
  /** Surfaces a non-trivial second skill — e.g. a primary-bowler
   *  who also bats. Null when only one skill is in evidence. */
  secondary_role: PlayerRole | null;
}

/** Mirrors Pydantic `ComparisonResponse` — the flagship response. */
export interface ComparisonResponse {
  format: MatchType;
  player1: PlayerComparisonSlot;
  player2: PlayerComparisonSlot;
  common_opponents: CommonOpponentBlock[];
  /** Empty when both players have ≥5 innings in the format; populated
   *  when the dashboard should render an "insufficient data" notice. */
  data_quality: DataQualityWarning[];
}

/** Mirrors Pydantic `FormatBreakdown`. */
export interface FormatBreakdown {
  format: MatchType;
  batting: BattingCareerStats | null;
  bowling: BowlingCareerStats | null;
}

/** Mirrors Pydantic `PlayerAverageResponse`. */
export interface PlayerAverageResponse {
  profile: PlayerProfileCard;
  by_format: FormatBreakdown[];
  data_quality: DataQualityWarning[];
}

/** Mirrors Pydantic `FormGuideResponse`. */
export interface FormGuideResponse {
  profile: PlayerProfileCard;
  innings: FormGuideEntry[];
  data_quality: DataQualityWarning[];
}

/** Mirrors Pydantic `HeadToHeadResponse`. */
export interface HeadToHeadResponse {
  team1: string;
  team2: string;
  format: MatchType;
  total_matches: number;
  team1_wins: number;
  team2_wins: number;
  no_results: number;
  average_first_innings_score: number | null;
  bat_first_win_pct: number | null;
  bowl_first_win_pct: number | null;
}

/** Mirrors Pydantic `VenueStatsResponse`. */
export interface VenueStatsResponse {
  ground: string;
  matches: number;
  average_first_innings_score: number | null;
  bat_first_win_pct: number | null;
  bowl_first_win_pct: number | null;
}

/** Mirrors Pydantic `BowlerPhaseStats`. */
export interface BowlerPhaseStats {
  phase: "powerplay" | "middle" | "death";
  overs_bowled: number;
  wickets: number;
  economy: number | null;
}

/** Mirrors Pydantic `BowlerPhasesResponse`. */
export interface BowlerPhasesResponse {
  profile: PlayerProfileCard;
  phases: BowlerPhaseStats[];
}

// ====================================================================
// player.py
// ====================================================================

/** Mirrors Pydantic `PlayerResponse`. */
export interface PlayerResponse {
  id: number;
  external_id: string | null;
  name: string;
  country: string | null;
  role: PlayerRole | null;
  batting_style: string | null;
  bowling_style: string | null;
  /** ISO date string, e.g. "1994-10-15". */
  date_of_birth: string | null;
  /** ISO 8601 datetime string. */
  created_at: string;
  /** ISO 8601 datetime string. */
  updated_at: string;
}

/** Mirrors Pydantic `PlayerWithStats`. */
export interface PlayerWithStats extends PlayerResponse {
  primary_role: PlayerRole;
  batting: BattingCareerStats | null;
  bowling: BowlingCareerStats | null;
}

// ====================================================================
// match.py
// ====================================================================

/** Mirrors Pydantic `MatchResponse`. */
export interface MatchResponse {
  id: number;
  external_id: string;
  match_type: MatchType;
  venue: string | null;
  ground: string | null;
  /** ISO 8601 datetime string. */
  date: string;
  team1: string;
  team2: string;
  winner: string | null;
  toss_winner: string | null;
  toss_decision: TossDecision | null;
  result_margin: string | null;
  created_at: string;
  updated_at: string;
}

// ====================================================================
// stats.py — per-row scorecard responses
// ====================================================================

/** Mirrors Pydantic `BattingStatsResponse`. */
export interface BattingStatsResponse {
  id: number;
  player_id: number;
  match_id: number;
  runs: number;
  balls_faced: number | null;
  fours: number;
  sixes: number;
  strike_rate: number | null;
  dismissal_type: string | null;
  innings_number: number;
  position: number | null;
}

/** Mirrors Pydantic `BowlingStatsResponse`. */
export interface BowlingStatsResponse {
  id: number;
  player_id: number;
  match_id: number;
  overs: number;
  maidens: number;
  runs_conceded: number;
  wickets: number;
  economy_rate: number | null;
  extras: number | null;
  innings_number: number;
}

// ====================================================================
// /health
// ====================================================================

export interface HealthResponse {
  status: "ok" | "degraded";
  db: "connected" | "unreachable";
}

// ====================================================================
// live.py — live scores feed
// ====================================================================

/** Mirrors Pydantic `LiveMatch`. */
export interface LiveMatch {
  match_id: string;
  name: string;
  status: string;
  match_type: string;
  venue: string | null;
  teams: string[];
  /** team_name → "180/6 (20 ov)" */
  scores: Record<string, string>;
  is_live: boolean;
}

/** Mirrors Pydantic `LiveScoreResponse`. */
export interface LiveScoreResponse {
  live_available: boolean;
  matches: LiveMatch[];
}
