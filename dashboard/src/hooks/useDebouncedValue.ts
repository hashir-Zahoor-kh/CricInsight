import { useEffect, useState } from "react";

/**
 * Debounce any value by `delayMs`. The returned value lags behind
 * `value` until the user stops changing it for the delay window.
 *
 * Used by the player search picker so a fresh `/api/v1/players/search`
 * call doesn't fire on every keystroke — only after the typing
 * settles for 300 ms.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
