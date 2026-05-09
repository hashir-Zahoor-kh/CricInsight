import { Link } from "react-router-dom";
import { ArrowRight, Search } from "lucide-react";

import { EmptyState } from "../components/EmptyState";
import { Skeleton } from "../components/LoadingSkeleton";
import { usePlayers } from "../hooks/useApi";

/**
 * Lightweight directory of every seeded player. Click a row to drop
 * onto its individual deep-dive page.
 */
export function PlayersListPage() {
  const playersQuery = usePlayers({ limit: 200 });
  const players = playersQuery.data ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
          Players
        </h1>
        <p className="text-ink-600">
          Roster of every seeded player. Click any row to see their
          individual stats, or pick two on the home page to compare.
        </p>
      </header>

      {playersQuery.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : players.length === 0 ? (
        <EmptyState
          title="No players yet"
          icon={<Search className="h-6 w-6 text-pk-700" aria-hidden />}
        />
      ) : (
        <ul className="overflow-hidden rounded-2xl bg-white shadow-card">
          {players.map((p) => (
            <li
              key={p.id}
              className="border-b border-ink-100 last:border-b-0"
            >
              <Link
                to={`/player/${p.id}`}
                className="flex items-center justify-between px-5 py-3 text-sm transition-colors hover:bg-pk-50"
              >
                <div>
                  <div className="font-medium text-ink-900">{p.name}</div>
                  <div className="text-xs text-ink-500">
                    {p.country ?? "—"}{" "}
                    {p.role && <>· {p.role}</>}
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 text-ink-400"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
