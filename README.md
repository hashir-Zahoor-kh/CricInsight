# CricInsight

A full-stack cricket analytics dashboard centred on side-by-side
**player comparison**. Pick any two international batters, bowlers,
or all-rounders, scope to a format (T20I / ODI / Test), and see
career stats, last-10-innings form, and head-to-head against common
opponents — rendered with a Pakistan-green theme and a recharts radar.

The flagship endpoint is `GET /api/v1/analytics/compare` and the
flagship view is the `/compare` page in the dashboard.

> **Status:** local stack works end-to-end. 201 backend tests
> passing. Dashboard tuned for a 1280 px laptop viewport. Real data
> via Cricsheet — 100 T20Is / 60 ODIs / 40 Tests across 17 of the 22
> seeded international players.

---

## Why I built this

The project started as a way to combine two of my interests: Pakistan
cricket and production-grade backend engineering. Growing up
following Babar Azam and Mohammad Rizwan in T20Is, Wasim Akram and
Waqar Younis in archive footage, I wanted a dashboard that could
answer questions like "How does Babar's Pakistan T20I record stack
up against Kohli's India T20I record at common venues?" without
copying numbers from ESPNcricinfo into a spreadsheet.

What started Pakistan-focused became a **global player comparison
tool** mid-build — the data and the analytics generalise cleanly
to any pair of international cricketers, and limiting the dashboard
to one country was leaving the most interesting matchups (Smith vs
Kohli, Williamson vs Root, Stokes vs Bumrah) on the table.

---

## Architecture

```
                  ┌──────────────────┐
                  │   React + Vite   │
                  │   (TypeScript)   │
                  │   :3000          │
                  └────────┬─────────┘
                           │  axios (typed against backend schemas)
                           │  React Query
                           ▼
                  ┌──────────────────┐
                  │     FastAPI      │
                  │     :8000        │
                  │ (async, Py 3.12) │
                  └────────┬─────────┘
                           │  async SQLAlchemy
                           │  asyncpg, pool 5+10
                           ▼
                  ┌──────────────────┐
                  │   PostgreSQL 15  │
                  │   :5432          │
                  └──────────────────┘
                           ▲
                           │  one-shot ingestion
                           │  (Cricsheet JSON archives)
                  ┌────────┴─────────┐
                  │  ingestion CLI   │
                  │ • cricsheet_loader
                  │ • normalizer
                  │ • loader (upsert)
                  └──────────────────┘
```

Each layer in `backend/`:

```
backend/
├── app/
│   ├── main.py             # FastAPI app + lifespan + DB-aware /health
│   ├── config.py           # Pydantic-settings (DATABASE_URL, CORS, …)
│   ├── database.py         # async engine, pool 5+10, get_db dep
│   ├── models/             # SQLAlchemy 2.0 ORM (Mapped/mapped_column)
│   ├── schemas/            # Pydantic — flagship ComparisonResponse
│   ├── services/           # heavy SQL (e.g. comparison aggregation)
│   └── routers/            # players, matches, analytics
├── ingestion/
│   ├── cricsheet_loader.py # Cricsheet JSON parser
│   ├── seed_cricsheet.py   # full-load CLI
│   ├── normalizer.py       # raw → NormalizedMatchResult
│   ├── loader.py           # idempotent ON-CONFLICT upserts
│   └── client.py           # CricAPI client (vestigial; see pivot note)
├── alembic/                # migrations
└── tests/                  # 201 tests (models, ingestion, API, /compare)
```

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Database | PostgreSQL 15 | Mature, Alembic + asyncpg + ON CONFLICT for the upsert path |
| ORM | SQLAlchemy 2.0 (async) | Modern `Mapped[]` syntax, asyncpg driver, savepoints for batch loads |
| Migrations | Alembic | `--autogenerate` against `Base.metadata`, naming convention for stable constraints |
| API | FastAPI | Pydantic-typed responses, auto-generated OpenAPI at `/docs`, async-native |
| Validation | Pydantic v2 | Strict request + response schemas; `ComparisonResponse` is the single source of truth |
| HTTP client | httpx | Async-capable, used by both the CricAPI client and the dashboard test runner |
| Frontend | React 19 + TypeScript + Vite | Fast HMR, tree-shaking, no CRA cruft |
| Charts | recharts | Radar (5 axes), sparklines, format-friendly for screenshots |
| Data fetching | TanStack Query | Stable cache keys, automatic loading/error states, 60 s staleTime tuned for analytics |
| Styling | Tailwind v4 | Pakistan-green palette tokens (`pk-50` → `pk-950`) baked into the theme |
| Local infra | Docker Compose | One command spins up Postgres + backend + dashboard |
| Cloud (planned) | Terraform → AWS RDS + ECS Fargate | Phase 6 left intentionally unwritten — local stack is enough for the portfolio |
| Data source | [Cricsheet](https://cricsheet.org/) | Free, unlimited, ball-by-ball JSON. See the pivot note below. |

---

## Local setup

### Prerequisites

- Docker Desktop (for Postgres)
- Python 3.12 (the backend Dockerfile uses 3.12-slim; local venv should match)
- Node 20+ (for the dashboard)

### One-time setup

```bash
git clone https://github.com/hashir-Zahoor-kh/CricInsight.git
cd CricInsight

# Bring up Postgres
docker compose up -d db

# Backend dependencies
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# Apply schema migrations
cd backend
alembic upgrade head
cd ..

# Dashboard dependencies
cd dashboard
npm install
cd ..
```

### Optional: configure env

The defaults work for local dev. To override, copy `.env.example`
to `.env` (or `backend/.env` — code checks both). The only env vars
that meaningfully change behaviour are `DATABASE_URL` (and the sync
variant `DATABASE_URL_SYNC` for Alembic) and `CORS_ORIGINS`.

CricAPI was the original ingestion source but the pivot note below
makes that key optional — you can run the whole project without one.

### Seed the database

```bash
source backend/.venv/bin/activate
cd backend
python -m ingestion.seed_cricsheet
```

First run downloads three Cricsheet archives (~50 MB total),
extracts them, and ingests 200 matches involving the seeded player
roster. Repeat runs use the on-disk extracted JSON — no network.

Default targets are 100 T20I / 60 ODI / 40 Test matches. Override
with `--t20i N --odi N --test N`. The DB gets `TRUNCATE … RESTART
IDENTITY` on each run unless you pass `--no-wipe`.

### Run

```bash
# Terminal 1 — backend
source backend/.venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — dashboard
cd dashboard
npm run dev
```

Open <http://localhost:3000>. Pick two players, format, hit Compare.

API docs: <http://localhost:8000/docs>

### Run tests

```bash
source backend/.venv/bin/activate
cd backend
python -m pytest -q
```

Tests use a separate `cricinsight_test` database — they create it
fresh (via `alembic upgrade head`, not `metadata.create_all`, so
schema drift between ORM and migrations gets caught here), TRUNCATE
between tests, drop on session teardown.

---

## Deployment

The production stack is **Render** (backend) + **Vercel** (frontend) + **AWS**
(ECR image registry, S3 for Cricsheet archives, CloudWatch for logs).

```
  Vercel (React SPA)
      │  HTTPS API calls
      ▼
  Render Web Service  ──► AWS CloudWatch (/cricinsight/backend)
      │  docker image
      ▼
  AWS ECR  (802531653822.dkr.ecr.us-east-1.amazonaws.com/cricinsight-backend)
      │  DATABASE_URL
      ▼
  Render PostgreSQL (cricinsight-db, free plan)
```

### Backend → Render

`render.yaml` at the repo root defines the service. Connect the GitHub repo
in the Render dashboard and it will auto-detect the file.

Set these env vars in the Render dashboard (marked `sync: false` in the YAML,
meaning Render won't auto-populate them):

| Variable | Value |
|---|---|
| `DATABASE_URL_SYNC` | Same host as `DATABASE_URL` but with `+psycopg2` driver (for Alembic) |
| `CRICAPI_KEY` | CricAPI free-tier key (live scores feed) |
| `ALLOWED_ORIGINS` | `https://<your-vercel-app>.vercel.app` |
| `AWS_ACCESS_KEY_ID` | IAM key for CloudWatch + S3 access |
| `AWS_SECRET_ACCESS_KEY` | Matching IAM secret |

The service auto-redeploys on every push to `main`. `/health` is the health
check path — Render replaces the instance if it returns non-200.

### Frontend → Vercel

1. Import the repo in Vercel → set **Root Directory** to `dashboard`.
2. Build command: `npm run build` · Output directory: `dist`.
3. `dashboard/vercel.json` rewrites all paths to `index.html` so React Router
   deep-links survive hard refresh.

### Docker image → AWS ECR

The Render service pulls the image from ECR. Push a new image after any
backend change:

```bash
export AWS_ACCOUNT_ID=802531653822
export AWS_REGION=us-east-1
bash scripts/push_to_ecr.sh
# → 802531653822.dkr.ecr.us-east-1.amazonaws.com/cricinsight-backend:latest
```

### Cricsheet archives → AWS S3

The seed CLI reads Cricsheet JSON from disk. To seed a fresh Render instance,
upload the archives to S3 first, then pull them down inside the service:

```bash
export CRICSHEET_S3_BUCKET=cricinsight-data-802531653822
python scripts/upload_cricsheet_to_s3.py   # uploads 6 691 files
```

### CloudWatch logs

Set `AWS_CLOUDWATCH_LOG_GROUP=/cricinsight/backend` in Render. The
`watchtower` handler in `app/main.py` will ship every log line to the
`/cricinsight/backend` log group in `us-east-1`.

---

## The Cricsheet pivot

The project originally targeted CricAPI's free tier. After
implementing the seed against `/playerStats` and `/match`, both
endpoints turned out to require a **paid plan** — they return
`{"status": "failure", "reason": "Invalid API requested"}` on the
free tier. The free tier exposes only `/players`, `/cricScore`,
and `/matches` (a top-level listing with no scorecards). Without
scorecards there are no batting or bowling rows to ingest, which
means the comparison page has nothing to display.

The fix was to switch to **[Cricsheet](https://cricsheet.org)** —
a community-maintained archive that ships ball-by-ball JSON for
every men's international (and lots of domestic). It's free, has
no rate limits, and is the data source that serious cricket
analytics projects actually use.

What changed in the codebase:

- New parser at `backend/ingestion/cricsheet_loader.py` that walks
  Cricsheet's per-format archive directories, ball-by-ball, and
  emits the same `NormalizedMatchResult` Pydantic shape the rest
  of the pipeline already understood. The existing
  `loader.py` (idempotent ON CONFLICT upserts) didn't change.
- New CLI at `backend/ingestion/seed_cricsheet.py` replaces
  `seed.py` for the real load. `seed.py` is kept around for the
  free-tier `/cricScore` live-feed path, vestigial for now.
- Cricsheet's per-match JSON tags both T20Is and franchise T20s
  with `match_type: "T20"`. The international flag is implicit in
  which archive directory the file came from
  (`t20s_male_json.zip`). The parser takes a `forced_match_type`
  override the seed CLI passes per directory so all 100 T20Is
  land in the right bucket.
- Player names in Cricsheet alternate between full form
  ("Babar Azam") and abbreviated ("BA Stokes", "B Azam"). The
  filter matches by surname + first-initial pair; the roster
  builder remaps to the seeded full forms; player country gets
  backfilled from the per-match `info.players.<team>` map.

The pivot turned out to be a strict upgrade: real ball-by-ball
data, no quota anxiety, and the codebase ended up exercising both
data sources (the live `/cricScore` and the bulk Cricsheet
ingestion) which makes the architecture diagram more interesting
than it would have been with one source.

---

## What I'd do next

- **AWS deployment** (Phase 6 in the original plan). Terraform for
  RDS + ECS Fargate is sketched in `infrastructure/` but not
  applied — the local stack is enough for the portfolio. The
  backend pool sizing (`pool_size=5`, `max_overflow=10`) is
  already tuned for a 256 CPU / 512 MB Fargate task.
- **Live `/cricScore` feed** — surface in-progress matches on the
  Home page, rotating every 30 s. The CricAPI client supports it
  on the free tier; the seed already uses it for the smoke test.
- **Tail-end milestone tracking** — surface boundary-share, pull
  shots, scoring zones from Cricsheet's per-ball coordinates.
- **Multi-player radar** — three or four players overlaid on the
  same chart for an era-comparison view (current Babar vs prime
  Inzamam vs prime Younis Khan).
- **Player-pair URL parity** — the comparison page already accepts
  `?p1=…&p2=…&fmt=…`, so adding shareable short links and OpenGraph
  preview cards would be a small lift but a big win for posting to
  Twitter / LinkedIn.
- **Switch to ball-by-ball storage** — currently we aggregate
  Cricsheet ball-by-ball into per-(match, player, innings)
  rollups. Storing the raw deliveries would unlock partnership
  analysis, dot-ball %, scoring against pace vs spin, etc. The
  schema migration is straightforward; the analytics queries would
  be the bulk of the work.

---

## Repo links

- Source: <https://github.com/hashir-Zahoor-kh/CricInsight>
- API docs (when running locally): <http://localhost:8000/docs>
