import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { LiveScoresPanel } from "../components/LiveScoresPanel";
import { PlayerSearchPicker } from "../components/PlayerSearchPicker";
import { MatchType } from "../api/types";

/**
 * Landing page — Visual Redesign hero.
 *
 * Above the fold: a 100vh dark hero with the wordmark in Bebas Neue,
 * a one-line subtitle, two player search inputs, a three-pill format
 * selector, and a Compare CTA. Submitting the form (or clicking
 * Compare) navigates to `/compare?p1=…&p2=…&fmt=…` with React Router.
 *
 * Below the fold sits a placeholder slot where the LiveScoresPanel
 * (Feature 2) will eventually land. Kept as an empty section now so
 * the layout is already correct when that work begins.
 */
export function HomePage() {
  const navigate = useNavigate();

  const [p1, setP1] = useState<number | null>(null);
  const [p2, setP2] = useState<number | null>(null);
  const [fmt, setFmt] = useState<MatchType>(MatchType.T20I);

  const canCompare = p1 != null && p2 != null && p1 !== p2;

  const onCompare = () => {
    if (!canCompare) return;
    navigate(`/compare?p1=${p1}&p2=${p2}&fmt=${fmt}`);
  };

  return (
    <>
      {/* ============================ HERO ============================ */}
      {/* The hero fills the viewport below the 48px top nav so the
          headline sits at vertical center on first paint. */}
      <section className="flex min-h-[calc(100vh-3rem)] w-full items-center bg-canvas">
        <div className="mx-auto w-full max-w-[1440px] px-12">
          <h1 className="font-display text-[96px] uppercase leading-none tracking-tight text-fg">
            CRICINSIGHT
          </h1>
          <p className="mt-6 font-sans text-lg text-fg-secondary">
            Compare the world's best cricketers. Stat by stat.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              onCompare();
            }}
            className="mt-12 max-w-3xl space-y-8"
          >
            <div className="grid grid-cols-2 gap-6">
              <PlayerSearchPicker
                label="Player 1"
                value={p1}
                onChange={setP1}
                excludeId={p2}
              />
              <PlayerSearchPicker
                label="Player 2"
                value={p2}
                onChange={setP2}
                excludeId={p1}
              />
            </div>

            <FormatPicker value={fmt} onChange={setFmt} />

            <button
              type="submit"
              disabled={!canCompare}
              className="border border-accent px-6 py-2.5 font-sans text-sm uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-canvas disabled:cursor-not-allowed disabled:border-line disabled:bg-transparent disabled:text-fg-muted disabled:hover:bg-transparent disabled:hover:text-fg-muted"
            >
              Compare
            </button>
          </form>
        </div>
      </section>

      {/* ====================== BELOW THE FOLD ======================= */}
      <LiveScoresPanel />
    </>
  );
}

// --------------------------------------------------------------------

function FormatPicker({
  value,
  onChange,
}: {
  value: MatchType;
  onChange: (fmt: MatchType) => void;
}) {
  // Spec: three pills only — T20I, ODI, TEST. Domestic T20 (franchise)
  // is intentionally excluded from the homepage selector; users who
  // need it can still hit /compare?fmt=T20 directly.
  const options: { value: MatchType; label: string }[] = [
    { value: MatchType.T20I, label: "T20I" },
    { value: MatchType.ODI, label: "ODI" },
    { value: MatchType.TEST, label: "Test" },
  ];

  return (
    <div>
      <div className="font-sans text-[11px] uppercase tracking-widest text-fg-secondary">
        Format
      </div>
      <div className="mt-2 flex gap-3">
        {options.map((o) => {
          const isSelected = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onChange(o.value)}
              className={`border px-4 py-1.5 font-sans text-xs uppercase tracking-widest transition-colors ${
                isSelected
                  ? "border-accent text-accent"
                  : "border-line text-fg-muted hover:border-fg-muted hover:text-fg"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
