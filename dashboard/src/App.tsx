import { Activity } from "lucide-react";

/**
 * Phase 5.1 placeholder — proves the Tailwind theme tokens load and
 * the build chain is wired end-to-end. Real pages and routing land
 * in Phase 5.3.
 *
 * The colour usage here is the spec for downstream components:
 *   - `bg-pk-50` page background (warm off-white that pairs with green)
 *   - `bg-pk-900` PAKISTAN GREEN accent (canonical brand colour)
 *   - `text-ink-*` body / heading text
 */
export default function App() {
  return (
    <div className="min-h-screen bg-pk-50">
      <header className="bg-pk-900 text-white shadow-card">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <Activity className="h-6 w-6" aria-hidden />
          <h1 className="text-xl font-semibold tracking-tight">
            CricInsight
          </h1>
          <span className="ml-3 rounded-full bg-white/15 px-2 py-0.5 text-xs uppercase tracking-wider">
            theme check
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-12 space-y-8">
        <section className="rounded-2xl bg-white p-8 shadow-card">
          <h2 className="text-2xl font-semibold text-ink-900">
            Pakistan green theme tokens loaded
          </h2>
          <p className="mt-2 text-ink-600">
            If you can read this, Tailwind is wired and the{" "}
            <code className="rounded bg-pk-100 px-1.5 py-0.5 text-pk-900">
              pk
            </code>{" "}
            and{" "}
            <code className="rounded bg-ink-100 px-1.5 py-0.5 text-ink-700">
              ink
            </code>{" "}
            palettes are available to every component.
          </p>

          <div className="mt-6 grid grid-cols-5 gap-2 sm:grid-cols-11">
            {/* Class names listed literally so Tailwind's JIT can see
                them — template-string interpolation gets purged. */}
            {[
              { shade: 50, cls: "bg-pk-50" },
              { shade: 100, cls: "bg-pk-100" },
              { shade: 200, cls: "bg-pk-200" },
              { shade: 300, cls: "bg-pk-300" },
              { shade: 400, cls: "bg-pk-400" },
              { shade: 500, cls: "bg-pk-500" },
              { shade: 600, cls: "bg-pk-600" },
              { shade: 700, cls: "bg-pk-700" },
              { shade: 800, cls: "bg-pk-800" },
              { shade: 900, cls: "bg-pk-900" },
              { shade: 950, cls: "bg-pk-950" },
            ].map(({ shade, cls }) => (
              <div key={shade} className="text-center">
                <div
                  className={`h-12 w-full rounded-md ring-1 ring-black/5 ${cls}`}
                />
                <div className="mt-1 text-[11px] text-ink-500">{shade}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl bg-white p-8 shadow-card">
          <h3 className="text-lg font-semibold text-ink-900">Next up</h3>
          <ul className="mt-3 list-disc pl-5 text-ink-700 space-y-1">
            <li>Phase 5.2 — useApi() React Query hook</li>
            <li>Phase 5.3 — Home, Comparison, and Player pages</li>
            <li>Phase 5.4 — sidebar navigation and responsive layout</li>
          </ul>
        </section>
      </main>
    </div>
  );
}
