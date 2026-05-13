# CricInsight — Claude Code Project Context

## CRITICAL RULES — READ BEFORE DOING ANYTHING

1. **Git author must always be:** `Hashir Zahoor <hashirzahoor74@icloud.com>`
   Run this before any commit: `git config user.name "Hashir Zahoor" && git config user.email "hashirzahoor74@icloud.com"`

2. **Never touch:** `backend/`, `src/api/`, `src/data/`, any test files — unless the task explicitly says so

3. **Always run `npm run build` after any frontend change.** 0 TypeScript errors required before reporting.

4. **Always run `pytest backend/ -q` after any backend change.** 0 failures required before reporting.

5. **Pause and wait for "confirmed" or "proceed" after every step.** Never chain steps without confirmation.

6. **One branch per feature.** Merge to main only after tests pass and user confirms.

---

## Project Summary

**CricInsight** is a full-stack cricket analytics platform. Pick any two international cricketers, select a format (T20I/ODI/Test), and get a side-by-side comparison: career stats, radar chart, form sparklines, common opponents table.

**Repo:** https://github.com/hashir-Zahoor-kh/CricInsight
**Local path:** `/Users/hashir/CricInsights`

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async) + SQLAlchemy 2.0 + asyncpg |
| Database | PostgreSQL 15 + Alembic migrations |
| Frontend | React 19 + TypeScript + Vite + Tailwind v3 |
| Charts | recharts (radar + sparklines) |
| Data fetching | TanStack Query + axios |
| Data source | Cricsheet (free, ball-by-ball JSON) |
| Local infra | Docker Compose |

---

## Current State (last updated: May 2026)

### Backend — COMPLETE
- 198 tests passing, 3 skipped (pre-pivot CricAPI tests), 0 failures
- All endpoints working: `/api/v1/players`, `/api/v1/matches`, `/api/v1/analytics/compare`, `/api/v1/live/scores`
- Flagship endpoint: `GET /api/v1/analytics/compare?player1_id=X&player2_id=Y&format=T20I`

### Data — COMPLETE
- 2,962 matches (2,351 T20I + 611 ODI), dates 2021–2026
- 49,251 batting rows, 35,424 bowling rows
- 3,559 players across 105 countries
- Source: Cricsheet (pivoted from CricAPI — free tier missing `/match` and `/playerStats`)

### Dashboard — FUNCTIONAL, NEEDS VISUAL REDESIGN
- All pages work: HomePage, ComparisonPage, PlayerPage, PlayersListPage
- Debounced player search working (fixed after bulk load)
- Current theme: Pakistan green sidebar, basic Tailwind — NOT the final design
- **Visual redesign NOT YET STARTED**

### Deployment — NOT DONE
- Plan: Railway (backend + PostgreSQL) + Vercel (frontend)
- Config files not yet written

---

## Git Branch Status

- `main` — stable, all core features merged
- `feature/bowler-comparison` — Step 1.1 complete (wickets_per_match, bowling_strike_rate, best_figures added to schema), Steps 1.2–1.4 NOT started

---

## Known Bugs

1. **Shaheen Afridi country shows "Germany"** — same-name collision in Cricsheet bulk load. A German club player named Shaheen Afridi exists in the dataset. Fix: add a caps-threshold filter (only load players who appear in 5+ international matches) in `cricsheet_loader.py`. Not yet fixed.

2. **JS bundle too large (732 kB)** — Vite warns chunk exceeds 500 kB. Fix: code-split recharts with dynamic import. Not yet fixed.

---

## What Needs To Be Done (in order)

### CURRENT PRIORITY: Visual Redesign

**Aesthetic:** "PSL Broadcast Command Center" — dark, dense, data-rich. Bloomberg Terminal meets ICC broadcast overlay.

**Design tokens:**
- Background: `#0A0A0A`
- Surface (cards): `#111111`
- Surface elevated: `#1A1A1A`
- Border: `#222222`
- Primary: `#004225`
- Primary glow: `#006B3C`
- Accent (SPARINGLY): `#CCFF00`
- Text primary: `#F0F0F0`
- Text secondary: `#888888`
- Text muted: `#444444`

**Typography:**
- Display: `Bebas Neue` (Google Font)
- Body/UI: `DM Sans` (Google Font)
- Numbers/stats: `JetBrains Mono` (Google Font)

**Key rules:**
- Border radius: 4px max everywhere
- Cards: `#111111` background, `1px solid #222222` border, NO box shadows
- Neon accent (#CCFF00): ONLY on the single most important number per card
- NO background gradients
- Grain texture on page background via SVG filter
- 1px neon lime left border on active/selected states

**Layout:** Remove sidebar. Replace with 48px top nav bar. Full-width content.

**Redesign steps (do in order, pause after each):**
1. Install Framer Motion: `npm install framer-motion`
2. Add Google Fonts to `dashboard/index.html`: Bebas Neue, DM Sans, JetBrains Mono
3. Update `tailwind.config.js` with new tokens
4. Write `src/styles/tokens.css` with CSS variables
5. Redesign `AppLayout.tsx` — top nav bar, remove sidebar
6. Redesign `HomePage.tsx` — 100vh dark hero, big Bebas Neue title, dual search inputs, format pills
7. Redesign `ComparisonPage.tsx` — Bento Grid layout (see spec below)
8. Add Framer Motion animations (see spec below)
9. Replace loading skeletons with dark shimmer
10. Redesign `PlayerPage.tsx`
11. `npm run build` — 0 errors
12. Start dev server, smoke test all pages

**ComparisonPage Bento Grid spec:**
- Row 1 (full width): Two player header cards side by side. Name in Bebas Neue 48px. Country muted DM Sans uppercase. ICC ranking badge neon lime pill bottom-left. BAT/BOWL monospace badge top-right.
- Row 2 (3 columns): narrow key stat (JetBrains Mono 64px neon lime single number) | wide radar chart (neon lime P1, #004225 P2, #1A1A1A grid) | narrow key stat P2
- Row 3 (2 equal columns): form sparklines with Framer Motion SVG pathLength animation 1.2s P1, 0.3s delay P2
- Row 4 (full width): common opponents table, dense monospace, alternating #111/#0A0A0A rows, neon lime for better value

**Animations spec:**
1. Page entry: staggered fade + slide up 12px per cell, delays 0/0.05/0.1/0.15s via Framer Motion variants
2. Stat numbers: useCountUp hook, count from 0 to value over 0.8s on first render
3. Form sparklines: Framer Motion pathLength 0→1 over 1.2s
4. Radar: opacity 0→1 over 0.6s after data loads
5. Card hover: border #333333 from #222222, no scale transforms

---

### AFTER REDESIGN: Resume Feature 1 from Step 1.2

**Feature 1 — Bowler Comparison Mode (branch: feature/bowler-comparison)**
- Step 1.1: DONE — wickets_per_match, dot_ball_pct added to BowlingCareerStats schema
- Step 1.2: NOT STARTED — improve role detection (pure bowler/batter detection, secondary_role field)
- Step 1.3: NOT STARTED — bowling radar axes in ComparisonRadar.tsx
- Step 1.4: NOT STARTED — commit and merge

**Feature 2 — Live Scores Feed**
- NOT STARTED
- Backend: GET /api/v1/live/scores endpoint, LiveScoreResponse schema, 60s cache TTL
- Frontend: LiveScoresPanel component, 60s polling, graceful fallback if unavailable

**Feature 3 — Share Button**
- NOT STARTED
- ShareButton.tsx component, clipboard API, 2s "Copied!" state, top-right of ComparisonPage header

**Feature 4 — ICC Rankings Badge**
- NOT STARTED
- `src/data/icc_rankings.json` with current rankings for 22 seeded players
- Rankings badge on PlayerProfileCard — neon lime pill, top-right corner
- Look up REAL current rankings from icc-cricket.com — do not guess

**Feature 5 — Career Timeline Chart**
- NOT STARTED
- Backend: GET /api/v1/analytics/player/{id}/timeline?format=T20I
- Frontend: recharts BarChart + ComposedChart on PlayerPage, format selector tabs

---

### AFTER FEATURES: Deployment

**Stack:** Railway (FastAPI + PostgreSQL) + Vercel (React)
**Files needed:**
- `railway.toml` at project root
- `vercel.json` in `dashboard/`
- Update `backend/app/config.py` to read PORT from environment
- Update CORS to allow Vercel deployment URL
- README deployment section

---

## How To Start Local Dev

```bash
# Terminal 1 — database
cd /Users/hashir/CricInsights
docker-compose up db -d

# Terminal 2 — backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 3 — frontend
cd dashboard
npm run dev
# Opens at http://localhost:3000

# Run seed (if DB is empty)
cd backend
source .venv/bin/activate
python -m ingestion.seed_cricsheet
```

---

## API Quick Reference

```
GET /api/v1/players?name=babar          search players
GET /api/v1/players/{id}                player profile
GET /api/v1/analytics/compare           flagship comparison endpoint
  ?player1_id=X&player2_id=Y&format=T20I
GET /api/v1/analytics/player/{id}/average
GET /api/v1/analytics/player/{id}/form
GET /api/v1/analytics/head-to-head
GET /api/v1/analytics/venue
GET /health                             DB health check
```

---

## Interview Story Points

- Built end-to-end: ingestion → normalization → API → dashboard
- Pivoted from CricAPI (paid-only endpoints) to Cricsheet mid-build without schema changes — proves source-agnostic architecture
- 198 tests including comprehensive `/compare` coverage with data quality thresholds
- Async SQLAlchemy with explicit pool sizing for AWS Fargate constraints
- TypeScript frontend types mirror Pydantic schemas field-for-field — drift surfaces at compile time
