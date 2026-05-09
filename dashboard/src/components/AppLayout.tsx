import { Activity, BarChart3, Home, Users } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { useHealth } from "../hooks/useApi";

/**
 * Two-pane shell — sidebar (PK green) + main content (pk-50). The
 * sidebar is intentionally simple in Phase 5.3; Phase 5.4 will polish
 * footer, mobile collapse (we're skipping that), and last-updated
 * timestamp.
 */
export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-pk-50">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden">
        <TopBar />
        <div className="mx-auto max-w-[1280px] px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="flex w-60 flex-shrink-0 flex-col bg-pk-950 text-pk-100">
      <div className="border-b border-white/10 p-5">
        <Link to="/" className="flex items-center gap-2">
          <div className="rounded-lg bg-pk-600 p-1.5">
            <Activity className="h-5 w-5 text-white" aria-hidden />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">CricInsight</div>
            <div className="text-[10px] uppercase tracking-wider text-pk-300">
              Player Comparison
            </div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        <NavItem to="/" icon={<Home className="h-4 w-4" aria-hidden />} label="Home" end />
        <NavItem
          to="/compare"
          icon={<BarChart3 className="h-4 w-4" aria-hidden />}
          label="Compare"
        />
        <NavItem
          to="/players"
          icon={<Users className="h-4 w-4" aria-hidden />}
          label="Players"
        />
      </nav>

      <div className="p-4 text-[11px] text-pk-300">
        <p>v0.1.0 · cricapi.com</p>
        <p className="mt-1 text-pk-400">data refreshes via seed script</p>
      </div>
    </aside>
  );
}

function NavItem({
  to,
  icon,
  label,
  end,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      // Active state spec from the user contract:
      //   bg-pk-800, white text, left border pk-400
      // Inactive:
      //   ink-300 text on pk-950 (sidebar bg) — sits low-contrast
      //   so the active row visually pops without looking gaudy.
      className={({ isActive }) =>
        `flex items-center gap-2 rounded-md border-l-2 px-3 py-2 text-sm transition-colors ${
          isActive
            ? "border-pk-400 bg-pk-800 text-white"
            : "border-transparent text-ink-300 hover:bg-pk-900/60 hover:text-white"
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}

function TopBar() {
  const health = useHealth();
  const status = health.isLoading
    ? "checking"
    : health.isError
      ? "unreachable"
      : health.data?.status === "ok"
        ? "healthy"
        : "degraded";

  const dotColour = {
    checking: "bg-ink-300",
    healthy: "bg-emerald-500",
    degraded: "bg-amber-500",
    unreachable: "bg-red-500",
  }[status];

  return (
    <div className="flex h-12 items-center justify-end border-b border-ink-200 bg-white px-8 text-sm text-ink-600">
      <span className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${dotColour}`} aria-hidden />
        API <span className="capitalize text-ink-800">{status}</span>
      </span>
    </div>
  );
}
