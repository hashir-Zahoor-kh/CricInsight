import { Link, NavLink, Outlet } from "react-router-dom";

import { useHealth } from "../hooks/useApi";

/**
 * Visual Redesign shell — single 48px top nav bar over a full-width
 * canvas. No sidebar. Logo (Bebas Neue) sits left, nav links sit
 * right in DM Sans uppercase widely-tracked muted; the active route
 * gets a neon-lime underline that overlays the bar's hairline.
 */
export function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-fg">
      <TopNav />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}

const NAV_ITEMS = [
  { to: "/", label: "Home", end: true },
  { to: "/compare", label: "Compare", end: false },
  { to: "/players", label: "Players", end: false },
] as const;

function TopNav() {
  return (
    <header className="h-12 border-b border-line bg-canvas">
      <div className="mx-auto flex h-full max-w-[1440px] items-center justify-between px-6">
        <Link
          to="/"
          className="font-display text-2xl uppercase leading-none tracking-[0.05em] text-fg transition-colors hover:text-accent"
        >
          CRICINSIGHT
        </Link>

        <nav className="flex h-full items-center">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              // Underline strategy: every link reserves a 2px bottom
              // border (transparent when inactive) so swapping in the
              // accent on active state doesn't shift the row's height.
              className={({ isActive }) =>
                `flex h-full items-center border-b-2 px-4 font-sans text-[11px] uppercase tracking-widest transition-colors ${
                  isActive
                    ? "border-accent text-fg"
                    : "border-transparent text-fg-muted hover:text-fg"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <HealthIndicator />
        </nav>
      </div>
    </header>
  );
}

function HealthIndicator() {
  const health = useHealth();
  const status = health.isLoading
    ? "checking"
    : health.isError
      ? "unreachable"
      : health.data?.status === "ok"
        ? "healthy"
        : "degraded";

  const dotColour = {
    checking: "bg-fg-muted",
    healthy: "bg-emerald-500",
    degraded: "bg-amber-500",
    unreachable: "bg-red-500",
  }[status];

  return (
    <span className="ml-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-fg-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColour}`} aria-hidden />
      <span>API</span>
      <span className="text-fg-secondary">{status}</span>
    </span>
  );
}
