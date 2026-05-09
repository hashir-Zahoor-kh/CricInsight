import { Activity, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

import { useHealth, useRecentMatches } from "./hooks/useApi";

/**
 * Phase 5.2 placeholder — proves the API client + React Query hooks
 * work end-to-end. Calls /health and /api/v1/matches/recent. Real
 * pages and routing land in Phase 5.3.
 */
export default function App() {
  const health = useHealth();
  const recent = useRecentMatches(5);

  return (
    <div className="min-h-screen bg-pk-50">
      <header className="bg-pk-900 text-white shadow-card">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <Activity className="h-6 w-6" aria-hidden />
          <h1 className="text-xl font-semibold tracking-tight">
            CricInsight
          </h1>
          <HealthBadge
            status={
              health.isLoading
                ? "loading"
                : health.isError
                  ? "error"
                  : health.data?.status === "ok"
                    ? "ok"
                    : "degraded"
            }
          />
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-8 px-6 py-12">
        <section className="rounded-2xl bg-white p-8 shadow-card">
          <h2 className="text-2xl font-semibold text-ink-900">
            API hooks wired
          </h2>
          <p className="mt-2 text-ink-600">
            React Query is talking to the FastAPI backend at{" "}
            <code className="rounded bg-pk-100 px-1.5 py-0.5 text-pk-900">
              {import.meta.env.VITE_API_URL ?? "http://localhost:8000"}
            </code>
            .
          </p>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <StatRow label="GET /health" result={health} />
            <StatRow label="GET /api/v1/matches/recent?limit=5" result={recent} />
          </div>
        </section>

        <section className="rounded-2xl bg-white p-8 shadow-card">
          <h3 className="text-lg font-semibold text-ink-900">
            Recent matches (live from the DB)
          </h3>
          {recent.isLoading ? (
            <p className="mt-3 text-ink-500">Loading…</p>
          ) : recent.isError ? (
            <p className="mt-3 text-red-600">
              Couldn't reach the API. Make sure the backend is running on{" "}
              <code className="rounded bg-red-50 px-1 text-red-700">
                {import.meta.env.VITE_API_URL ?? "http://localhost:8000"}
              </code>
              .
            </p>
          ) : recent.data && recent.data.length > 0 ? (
            <ul className="mt-3 divide-y divide-ink-100">
              {recent.data.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between py-2 text-sm"
                >
                  <span className="font-medium text-ink-800">
                    {m.team1} vs {m.team2}
                  </span>
                  <span className="text-ink-500">
                    {m.match_type} · {new Date(m.date).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-ink-500">
              No matches in the database yet. Run the seed script:
              <code className="ml-1 rounded bg-ink-100 px-1.5 py-0.5 font-mono text-ink-800">
                python -m ingestion.seed --partial
              </code>
            </p>
          )}
        </section>

        <section className="rounded-2xl bg-white p-8 shadow-card">
          <h3 className="text-lg font-semibold text-ink-900">Next up</h3>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-ink-700">
            <li>Phase 5.3 — Home, Comparison, and Player pages</li>
            <li>Phase 5.4 — sidebar navigation and responsive layout</li>
          </ul>
        </section>
      </main>
    </div>
  );
}

// --------------------------------------------------------------------

function HealthBadge({
  status,
}: {
  status: "loading" | "ok" | "degraded" | "error";
}) {
  const map = {
    loading: {
      cls: "bg-white/15",
      icon: <Loader2 className="h-3 w-3 animate-spin" aria-hidden />,
      label: "checking",
    },
    ok: {
      cls: "bg-emerald-500/25",
      icon: <CheckCircle2 className="h-3 w-3" aria-hidden />,
      label: "healthy",
    },
    degraded: {
      cls: "bg-amber-500/25",
      icon: <AlertTriangle className="h-3 w-3" aria-hidden />,
      label: "degraded",
    },
    error: {
      cls: "bg-red-500/25",
      icon: <AlertTriangle className="h-3 w-3" aria-hidden />,
      label: "unreachable",
    },
  } as const;
  const { cls, icon, label } = map[status];
  return (
    <span
      className={`ml-3 flex items-center gap-1.5 rounded-full ${cls} px-2 py-0.5 text-xs uppercase tracking-wider`}
    >
      {icon}
      {label}
    </span>
  );
}

function StatRow({
  label,
  result,
}: {
  label: string;
  result: { isLoading: boolean; isError: boolean; data?: unknown };
}) {
  const status = result.isLoading
    ? "loading"
    : result.isError
      ? "error"
      : result.data
        ? "ok"
        : "empty";
  const palette = {
    loading: "border-ink-200 bg-ink-50 text-ink-600",
    ok: "border-pk-200 bg-pk-50 text-pk-900",
    error: "border-red-200 bg-red-50 text-red-700",
    empty: "border-amber-200 bg-amber-50 text-amber-700",
  } as const;
  return (
    <div
      className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${palette[status]}`}
    >
      <code className="font-mono text-xs">{label}</code>
      <span className="ml-3 text-xs uppercase tracking-wider">{status}</span>
    </div>
  );
}
