/** @type {import('tailwindcss').Config} */
export default {
  // Vite + React + TS — scan every TS/TSX/JSX/HTML file under src/ plus
  // index.html. If a class only appears in markup outside this glob,
  // Tailwind's JIT will purge it from the bundle.
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Visual Redesign tokens — "PSL Broadcast Command Center"
        // aesthetic (CLAUDE.md). The legacy pk/ink palettes below
        // are intentionally kept while pages migrate over.
        canvas: "#0A0A0A",          // page background
        surface: "#111111",          // cards
        elevated: "#1A1A1A",         // surface elevated
        line: "#222222",             // border
        primary: "#004225",          // brand green
        "primary-glow": "#006B3C",   // hover / glow
        accent: "#CCFF00",           // neon lime — use sparingly
        fg: {
          DEFAULT: "#F0F0F0",        // text primary
          secondary: "#888888",      // text secondary
          muted: "#444444",          // text muted
        },
        // Pakistan flag green spectrum — anchored on #01411C as the
        // canonical brand colour (shade 900). Lighter shades for
        // backgrounds and outlines, darker for text on light bg and
        // active/pressed states. The 50→950 ladder matches Tailwind's
        // built-in palette conventions so component code reads
        // identically to e.g. `bg-blue-500` vs `bg-pk-500`.
        pk: {
          50:  "#f0f7f1",  // page bg / subtle tints
          100: "#dcebde",  // card hover, disabled bg
          200: "#bbd7c0",  // borders on light bg
          300: "#90bb98",
          400: "#5d966a",
          500: "#3a7849",  // links, secondary buttons
          600: "#2a5e37",  // primary CTA on white bg
          700: "#1f4a2c",
          800: "#13351e",
          900: "#01411C",  // PAKISTAN GREEN — canonical brand colour
          950: "#062a13",  // sidebar bg, deepest contrast
        },
        // Neutral scale used alongside the green for chrome (sidebar
        // dividers, body text, table rules). Slightly cool greys
        // pair nicely with the green without competing.
        ink: {
          50:  "#f6f7f8",
          100: "#eceef0",
          200: "#d4d8dc",
          300: "#aab1b8",
          400: "#7c848d",
          500: "#5a626b",
          600: "#3f4750",
          700: "#2a3138",
          800: "#1a1f24",
          900: "#0c1014",
        },
      },
      fontFamily: {
        // Redesign typography (Google Fonts, loaded in index.html):
        //   display — Bebas Neue (hero numbers, big titles)
        //   sans    — DM Sans (body / UI, replaces Inter)
        //   mono    — JetBrains Mono (stats / numeric data)
        // Each falls back to a system stack for the brief window
        // before Google Fonts resolve.
        display: [
          "Bebas Neue",
          "Impact",
          "system-ui",
          "sans-serif",
        ],
        sans: [
          "DM Sans",
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      // Subtle elevation used on cards + modals. Avoids the default
      // Tailwind drop-shadows which look heavy against PK green.
      boxShadow: {
        card: "0 1px 2px rgba(12, 16, 20, 0.04), 0 4px 12px rgba(12, 16, 20, 0.06)",
        "card-hover":
          "0 1px 2px rgba(12, 16, 20, 0.05), 0 8px 24px rgba(12, 16, 20, 0.10)",
      },
      // Charts grid lines + axis ticks defaulted to the ink palette
      // so Recharts renders consistent without per-component overrides.
      borderColor: {
        DEFAULT: "#d4d8dc",
      },
    },
  },
  plugins: [],
};
