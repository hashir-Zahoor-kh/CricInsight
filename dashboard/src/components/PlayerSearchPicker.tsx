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
 * The previous implementation was a hardcoded `<select>` of the first
 * 100 players — visibly broken once the bulk Cricsheet load pushed
 * the roster past 3,500. Switching to search avoids the "first page
 * of A-names" pathology and is the right UX for a roster this big.
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
    open && debouncedQuery.length >= 2 && (search.isFetching || filteredResults.length > 0 || !search.isLoading);

  // ----- selected-player chip view -----
  if (value != null && selected.data) {
    return (
      <div ref={containerRef}>
        <label className="block text-xs font-medium uppercase tracking-wider text-ink-500">
          {label}
        </label>
        <div className="mt-1 flex items-center justify-between rounded-md border border-pk-300 bg-pk-50 px-3 py-2 text-sm">
          <span className="flex items-center gap-2 text-ink-900">
            <span className="text-base leading-none" aria-hidden>
              {flagFor(selected.data.country)}
            </span>
            <span className="font-medium">{selected.data.name}</span>
            {selected.data.country && (
              <span className="text-xs text-ink-500">
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
            className="rounded p-0.5 text-ink-500 hover:bg-pk-100 hover:text-ink-800"
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
      <label className="block text-xs font-medium uppercase tracking-wider text-ink-500">
        {label}
      </label>
      <div className="relative mt-1">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
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
          className="w-full rounded-md border border-ink-200 bg-white py-2 pl-8 pr-3 text-sm text-ink-800 focus:border-pk-600 focus:outline-none focus:ring-1 focus:ring-pk-600"
        />
      </div>

      {showDropdown && (
        <div className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-ink-200 bg-white shadow-card">
          {search.isFetching && filteredResults.length === 0 ? (
            <div className="px-3 py-2 text-xs text-ink-500">searching…</div>
          ) : filteredResults.length === 0 ? (
            <div className="px-3 py-2 text-xs text-ink-500">
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
        <div className="absolute z-20 mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-xs text-ink-500 shadow-card">
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
      className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-pk-50 focus:bg-pk-50 focus:outline-none"
    >
      <span className="flex items-center gap-2 truncate">
        <span className="text-base leading-none" aria-hidden>
          {flagFor(player.country)}
        </span>
        <span className="truncate font-medium text-ink-800">{player.name}</span>
      </span>
      {player.country && (
        <span className="flex-shrink-0 text-xs text-ink-500">
          {player.country}
        </span>
      )}
    </button>
  );
}
