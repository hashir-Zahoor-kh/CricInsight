import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";

import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { usePlayer, usePlayerSearch } from "../hooks/useApi";
import { flagFor } from "../lib/countryFlag";
import type { PlayerResponse } from "../api/types";

/**
 * Type-ahead picker for the 3,500+ player roster.
 *
 * UX flow:
 *   1. User types a query into the input.
 *   2. After 300 ms with no further typing AND ≥2 chars, the search
 *      hook fires `GET /api/v1/players/search?name=…`.
 *   3. Suggestions render as a dropdown panel with `flag · name ·
 *      country`. Clicking a row commits the selection and collapses
 *      the dropdown.
 *   4. While a player is selected, the input shows the player as a
 *      chip; clicking the chip's × clears it and re-opens the search.
 *
 * Visuals are styled against the Visual Redesign dark tokens —
 * surface card, hairline line border, neon-lime focus ring.
 *
 * Props:
 *   value      Currently-picked player id (null = no selection).
 *   onChange   Called with a player id (or null) when the user picks
 *              or clears.
 *   excludeId  When set, that player is hidden from suggestions —
 *              used by ComparisonPage so player1 doesn't show up in
 *              player2's results and vice versa.
 *   label      The picker's visible label.
 *   placeholder  Input placeholder text. Defaults to "Type a name…".
 */
export function PlayerSearchPicker({
  value,
  onChange,
  excludeId = null,
  label,
  placeholder = "Type a name (e.g. Babar)…",
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  excludeId?: number | null;
  label: string;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const debouncedQuery = useDebouncedValue(query, 300);

  const search = usePlayerSearch(debouncedQuery);
  // Resolve the displayed name when `value` is set externally (e.g.
  // the URL params on /compare). usePlayer is enabled-gated on the
  // id, so passing null is a no-op.
  const selected = usePlayer(value);

  const containerRef = useRef<HTMLDivElement>(null);

  // Click-outside closes the dropdown. `mousedown` rather than
  // `click` so the picker collapses BEFORE the click target receives
  // its own handler — important when the user clicks the second
  // picker on the page, otherwise the first would steal focus.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  const filteredResults = useMemo(() => {
    const rows = search.data ?? [];
    return excludeId == null ? rows : rows.filter((p) => p.id !== excludeId);
  }, [search.data, excludeId]);

  const showDropdown =
    open &&
    debouncedQuery.length >= 2 &&
    (search.isFetching || filteredResults.length > 0 || !search.isLoading);

  const labelClass =
    "block font-sans text-[11px] uppercase tracking-widest text-fg-secondary";

  // ----- selected-player chip view -----
  if (value != null && selected.data) {
    return (
      <div ref={containerRef}>
        <label className={labelClass}>{label}</label>
        <div className="mt-2 flex items-center justify-between border border-line bg-surface px-3 py-2.5 text-sm">
          <span className="flex items-center gap-2 text-fg">
            <span className="text-base leading-none" aria-hidden>
              {flagFor(selected.data.country)}
            </span>
            <span className="font-medium">{selected.data.name}</span>
            {selected.data.country && (
              <span className="text-xs text-fg-secondary">
                · {selected.data.country}
              </span>
            )}
          </span>
          <button
            type="button"
            aria-label={`Clear ${selected.data.name}`}
            onClick={() => {
              onChange(null);
              setQuery("");
              setOpen(true);
            }}
            className="p-0.5 text-fg-muted transition-colors hover:text-accent"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>
    );
  }

  // ----- search input view -----
  return (
    <div ref={containerRef} className="relative">
      <label className={labelClass}>{label}</label>
      <div className="relative mt-2">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-muted"
          aria-hidden
        />
        <input
          type="text"
          autoComplete="off"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          placeholder={placeholder}
          className="w-full border border-line bg-surface py-2.5 pl-9 pr-3 text-sm text-fg placeholder:text-fg-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>

      {showDropdown && (
        <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto border border-line bg-surface">
          {search.isFetching && filteredResults.length === 0 ? (
            <div className="px-3 py-2 text-xs text-fg-muted">searching…</div>
          ) : filteredResults.length === 0 ? (
            <div className="px-3 py-2 text-xs text-fg-muted">
              No players match "{debouncedQuery}".
            </div>
          ) : (
            filteredResults.map((p) => (
              <SuggestionRow
                key={p.id}
                player={p}
                onPick={() => {
                  onChange(p.id);
                  setQuery("");
                  setOpen(false);
                }}
              />
            ))
          )}
        </div>
      )}

      {/* Helper hint when the user hasn't typed enough yet. */}
      {open && debouncedQuery.length < 2 && (
        <div className="absolute z-20 mt-1 w-full border border-line bg-surface px-3 py-2 text-xs text-fg-muted">
          Type at least 2 characters.
        </div>
      )}
    </div>
  );
}

function SuggestionRow({
  player,
  onPick,
}: {
  player: PlayerResponse;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-elevated focus:bg-elevated focus:outline-none"
    >
      <span className="flex items-center gap-2 truncate">
        <span className="text-base leading-none" aria-hidden>
          {flagFor(player.country)}
        </span>
        <span className="truncate font-medium text-fg">{player.name}</span>
      </span>
      {player.country && (
        <span className="flex-shrink-0 text-xs text-fg-secondary">
          {player.country}
        </span>
      )}
    </button>
  );
}
