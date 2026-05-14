import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import { EmptyState } from "../components/EmptyState";
import { Skeleton } from "../components/LoadingSkeleton";
import { usePlayers } from "../hooks/useApi";

/**
 * Lightweight directory of ICC Full Member nation players.
 * Click a row to open the individual deep-dive page.
 */
export function PlayersListPage() {
  const playersQuery = usePlayers({ limit: 200, test_nations_only: true });
  const players = playersQuery.data ?? [];

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 px-12 py-10">
      <header>
        <h1 className="font-display text-[64px] uppercase leading-none tracking-tight text-fg">
          Players
        </h1>
        <p className="mt-2 font-sans text-sm text-fg-secondary">
          ICC Full Member nation rosters. Click any row for individual stats,
          or pick two on the home page to compare.
        </p>
      </header>

      {playersQuery.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : players.length === 0 ? (
        <EmptyState title="No players yet" />
      ) : (
        <ul className="border border-line bg-surface">
          {players.map((p) => (
            <li key={p.id} className="border-b border-line last:border-b-0">
              <Link
                to={`/player/${p.id}`}
                className="flex items-center justify-between px-6 py-3 transition-colors hover:bg-elevated"
              >
                <div>
                  <div className="font-sans text-sm font-medium text-fg">
                    {p.name}
                  </div>
                  <div className="font-mono text-xs text-fg-muted">
                    {p.country ?? "—"}
                    {p.role && <> · {p.role}</>}
                  </div>
                </div>
                <ArrowRight className="h-4 w-4 text-fg-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
