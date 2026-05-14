/**
 * Typed React Query hooks for every backend endpoint.
 *
 * Pattern: one hook per FastAPI route. The hook returns the full
 * `UseQueryResult<T>` so components can read `.data`, `.isLoading`,
 * `.isError`, `.error` and render loading / error / empty states
 * uniformly.
 *
 * Query keys are stable arrays so React Query's cache works correctly:
 *   ["players", { name, country, ... }]
 * If a parameter is undefined / null, the hook is `enabled: false`
 * which skips the request — components can pass a draft search string
 * without triggering a 422 round-trip.
 *
 * The flagship hook is `useCompare` — types directly to
 * `ComparisonResponse` so any drift between frontend and backend
 * surfaces at compile time.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getJson } from "../api/client";
import type {
  ComparisonResponse,
  FormGuideResponse,
  HealthResponse,
  HeadToHeadResponse,
  LiveScoreResponse,
  MatchResponse,
  MatchType,
  PlayerAverageResponse,
  PlayerResponse,
  PlayerWithStats,
  TimelineResponse,
  VenueStatsResponse,
} from "../api/types";

// ====================================================================
// Health
// ====================================================================

export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => getJson<HealthResponse>("/health"),
    retry: false,
    refetchInterval: 30_000,
  });
}

export function useLiveScores(): UseQueryResult<LiveScoreResponse> {
  return useQuery<LiveScoreResponse>({
    queryKey: ["live-scores"],
    queryFn: () => getJson<LiveScoreResponse>("/api/v1/live/scores"),
    // Match the backend's 60s cache TTL so we're not hammering the
    // endpoint more often than it refreshes.
    refetchInterval: 60_000,
    // Stale data is fine — the panel shows last-known scores with no
    // error state while a re-fetch is in flight.
    staleTime: 55_000,
    retry: false,
  });
}

// ====================================================================
// Players
// ====================================================================

export interface PlayerListParams {
  name?: string;
  country?: string;
  /** When true (default), restricts results to the 12 ICC Full Member
   *  nations. Set false to include domestic / associate rosters. */
  test_nations_only?: boolean;
  limit?: number;
  offset?: number;
}

export function usePlayers(params: PlayerListParams = {}): UseQueryResult<PlayerResponse[]> {
  const effective: PlayerListParams = { test_nations_only: true, ...params };
  return useQuery<PlayerResponse[]>({
    queryKey: ["players", effective],
    queryFn: () => getJson<PlayerResponse[]>("/api/v1/players", effective),
  });
}

export function usePlayerSearch(
  name: string,
  options: { testNationsOnly?: boolean } = {}
): UseQueryResult<PlayerResponse[]> {
  const testNationsOnly = options.testNationsOnly ?? true;
  return useQuery<PlayerResponse[]>({
    queryKey: ["players", "search", name, testNationsOnly],
    queryFn: () =>
      getJson<PlayerResponse[]>("/api/v1/players/search", {
        name,
        test_nations_only: testNationsOnly,
      }),
    // Skip the request until the user has typed at least 2 chars —
    // saves quota on rapid typing and avoids server-side 422s.
    enabled: name.length >= 2,
  });
}

export function usePlayer(playerId: number | null): UseQueryResult<PlayerResponse> {
  return useQuery<PlayerResponse>({
    queryKey: ["players", playerId],
    queryFn: () => getJson<PlayerResponse>(`/api/v1/players/${playerId}`),
    enabled: playerId != null,
  });
}

export function usePlayerStats(
  playerId: number | null,
  format: MatchType | null
): UseQueryResult<PlayerWithStats> {
  return useQuery<PlayerWithStats>({
    queryKey: ["players", playerId, "stats", format],
    queryFn: () =>
      getJson<PlayerWithStats>(`/api/v1/players/${playerId}/stats`, { format }),
    enabled: playerId != null,
  });
}

// ====================================================================
// Matches
// ====================================================================

export interface MatchListParams {
  format?: MatchType;
  team?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export function useMatches(params: MatchListParams = {}): UseQueryResult<MatchResponse[]> {
  return useQuery<MatchResponse[]>({
    queryKey: ["matches", params],
    queryFn: () => getJson<MatchResponse[]>("/api/v1/matches", params),
  });
}

export function useRecentMatches(limit = 20): UseQueryResult<MatchResponse[]> {
  return useQuery<MatchResponse[]>({
    queryKey: ["matches", "recent", limit],
    queryFn: () => getJson<MatchResponse[]>("/api/v1/matches/recent", { limit }),
  });
}

export function useMatch(matchId: number | null): UseQueryResult<MatchResponse> {
  return useQuery<MatchResponse>({
    queryKey: ["matches", matchId],
    queryFn: () => getJson<MatchResponse>(`/api/v1/matches/${matchId}`),
    enabled: matchId != null,
  });
}

// ====================================================================
// Analytics — including the flagship /compare
// ====================================================================

/**
 * Side-by-side comparison of two players in a chosen format. THE
 * dashboard's centrepiece.
 *
 * Disabled until both player ids and a format are supplied — keeps
 * the dashboard from emitting a 422 while the user is still picking.
 */
export function useCompare(
  player1Id: number | null,
  player2Id: number | null,
  format: MatchType | null
): UseQueryResult<ComparisonResponse> {
  return useQuery<ComparisonResponse>({
    queryKey: ["compare", player1Id, player2Id, format],
    queryFn: () =>
      getJson<ComparisonResponse>("/api/v1/analytics/compare", {
        player1_id: player1Id,
        player2_id: player2Id,
        format,
      }),
    enabled:
      player1Id != null &&
      player2Id != null &&
      format != null &&
      player1Id !== player2Id,
  });
}

export function usePlayerAverage(
  playerId: number | null
): UseQueryResult<PlayerAverageResponse> {
  return useQuery<PlayerAverageResponse>({
    queryKey: ["player-average", playerId],
    queryFn: () =>
      getJson<PlayerAverageResponse>(
        `/api/v1/analytics/player/${playerId}/average`
      ),
    enabled: playerId != null,
  });
}

export function usePlayerForm(
  playerId: number | null,
  format: MatchType | null
): UseQueryResult<FormGuideResponse> {
  return useQuery<FormGuideResponse>({
    queryKey: ["player-form", playerId, format],
    queryFn: () =>
      getJson<FormGuideResponse>(`/api/v1/analytics/player/${playerId}/form`, {
        format,
      }),
    enabled: playerId != null && format != null,
  });
}

export function useHeadToHead(
  team1: string | null,
  team2: string | null,
  format: MatchType | null
): UseQueryResult<HeadToHeadResponse> {
  return useQuery<HeadToHeadResponse>({
    queryKey: ["head-to-head", team1, team2, format],
    queryFn: () =>
      getJson<HeadToHeadResponse>("/api/v1/analytics/head-to-head", {
        team1,
        team2,
        format,
      }),
    enabled:
      team1 != null && team2 != null && format != null && team1 !== team2,
  });
}

export function usePlayerTimeline(
  playerId: number | null,
  format: MatchType | null
): UseQueryResult<TimelineResponse> {
  return useQuery<TimelineResponse>({
    queryKey: ["player-timeline", playerId, format],
    queryFn: () =>
      getJson<TimelineResponse>(
        `/api/v1/analytics/player/${playerId}/timeline`,
        { format }
      ),
    enabled: playerId != null && format != null,
  });
}

export function useVenueStats(ground: string | null): UseQueryResult<VenueStatsResponse> {
  return useQuery<VenueStatsResponse>({
    queryKey: ["venue", ground],
    queryFn: () =>
      getJson<VenueStatsResponse>("/api/v1/analytics/venue", { ground }),
    enabled: ground != null && ground.length >= 1,
  });
}
