import { useState } from "react";
import { Share2 } from "lucide-react";

type CopyState = "idle" | "copied" | "error";

/**
 * Copies the current page URL to the clipboard.
 *
 * States: idle → "Share" / copied → "Copied!" (2s) / error → "Failed"
 * Styling: bg-accent text-canvas (neon lime fill).
 * Fallback: execCommand("copy") for browsers without Clipboard API.
 */
export function ShareButton() {
  const [state, setState] = useState<CopyState>("idle");

  const copy = async () => {
    const url = window.location.href;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        // Older browser fallback — create a hidden textarea, select it,
        // and use the deprecated execCommand so the URL still lands on
        // the clipboard without a user-visible flash.
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("execCommand failed");
      }
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  const label =
    state === "copied" ? "Copied!" : state === "error" ? "Failed" : "Share";

  const colours =
    state === "error"
      ? "border-red-500 bg-red-500/10 text-red-400"
      : state === "copied"
        ? "border-accent bg-accent text-canvas"
        : "border-accent bg-accent text-canvas hover:bg-accent/90";

  return (
    <button
      type="button"
      onClick={copy}
      aria-label="Copy link to this comparison"
      className={`flex items-center gap-1.5 border px-3 py-1.5 font-sans text-xs uppercase tracking-widest transition-colors ${colours}`}
    >
      <Share2 className="h-3 w-3" aria-hidden />
      {label}
    </button>
  );
}
