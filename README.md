# Daily Scholar 📚

A personalized daily learning system for students. Automatically delivers:
- **Fresh research papers** matching your interests
- **Topic reviews** from your current courses
- **Interactive quizzes** with spaced repetition
- **Supplementary resources** via web search

---

## Two ways to run Daily Scholar

| Path | For | What you get | Where to start |
|---|---|---|---|
| **Run locally** (clone + `make setup` + `make start`) | beta testers and developers who want full control | SQLite + local filesystem + local frontend; nothing leaves your machine | [Run Locally](#run-locally) |
| **Use the hosted version** | you and any invited collaborators | the production PWA at `scholar.<domain>` — install on your phone, push notifications, your data syncs across devices | [Hosted version](#hosted-version) |

The same codebase powers both. The hosted version layers Postgres, Backblaze B2, Cloudflare Access, and Railway on top, but every cloud-only feature has a local-mode fallback or graceful skip.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Directory Structure](#directory-structure)
3. [Run Locally](#run-locally)
4. [API Reference](#api-reference)
5. [Configuration](#configuration) (see also [docs/topics.md](docs/topics.md) for the unified Topic model)
6. [Install as a PWA](#install-as-a-pwa)
7. [Hosted version](#hosted-version) — Railway + Cloudflare + B2 deploy
8. [Tech Stack](#tech-stack)
9. [Learning Path](#learning-path)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DAILY SCHOLAR                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         FRONTEND (Next.js)                            │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │  │
│  │  │Dashboard│  │ Paper   │  │ Review  │  │  Quiz   │  │Settings │   │  │
│  │  │  Home   │  │ Reader  │  │  Mode   │  │  Mode   │  │ Upload  │   │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      BACKEND API (FastAPI)                            │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │
│  │  │  /papers   │  │  /topics   │  │  /quiz     │  │  /upload   │    │  │
│  │  │  endpoint  │  │  endpoint  │  │  endpoint  │  │  endpoint  │    │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         SERVICES LAYER                                │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │  │
│  │  │ Paper Discovery │  │ Content Gen     │  │ Quiz Engine     │      │  │
│  │  │ - arXiv API     │  │ - Claude API    │  │ - Spaced Rep    │      │  │
│  │  │ - Semantic Sch. │  │ - Summarization │  │ - Scoring       │      │  │
│  │  │ - CORE API      │  │ - Q&A Gen       │  │ - Progress      │      │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                          DATA LAYER                                   │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │  │
│  │  │ SQLite Database │  │ File Storage    │  │ Config (YAML)   │      │  │
│  │  │ - seen_papers   │  │ - course docs   │  │ - interests     │      │  │
│  │  │ - quiz_history  │  │ - uploaded PDFs │  │ - courses       │      │  │
│  │  │ - progress      │  │                 │  │ - schedule      │      │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
daily-scholar/
├── README.md                 # This file
├── .env                      # Environment variables (API keys) - DO NOT COMMIT
├── .env.example              # Template for environment variables
├── .gitignore                # Git ignore rules
├── requirements.txt          # Python dependencies
│
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Environment + YAML loaders
│   ├── database.py          # SQLAlchemy models + alembic glue
│   ├── models.py            # Pydantic models (data validation)
│   ├── api/
│   │   ├── __init__.py
│   │   └── topics.py        # Topic CRUD + scope endpoints (FastAPI router)
│   └── services/
│       ├── __init__.py
│       ├── paper_discovery.py    # arXiv, Semantic Scholar, CORE; topic-scoped
│       ├── content_generator.py  # LLM-driven reviews + quizzes
│       └── topic_loader.py       # YAML <-> topics-table sync (bootstrap/import/export)
│
├── alembic/                 # database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_baseline.py
│       └── 0002_topics_user_settings_push.py
├── alembic.ini
│
├── frontend/
│   ├── package.json         # Node.js dependencies
│   ├── tsconfig.json        # TypeScript configuration
│   ├── tailwind.config.js   # Tailwind CSS configuration
│   ├── postcss.config.js    # PostCSS configuration
│   ├── next.config.js       # Next.js configuration
│   ├── app/
│   │   ├── layout.tsx       # Root layout (with nav)
│   │   ├── page.tsx         # Dashboard
│   │   ├── globals.css      # Global styles
│   │   ├── papers/          # Paper discovery + archive pages
│   │   ├── quiz/            # Quiz session pages
│   │   ├── topics/
│   │   │   ├── page.tsx          # Topic catalog (list, grouped by stream)
│   │   │   ├── new/page.tsx      # Create new topic
│   │   │   ├── archive/page.tsx  # Past topic-review history
│   │   │   └── [id]/edit/page.tsx
│   │   └── settings/
│   │       └── scope/page.tsx    # Silo / multi / all scope selector
│   ├── components/
│   │   └── TopicForm.tsx    # Shared topic editor (new + edit)
│   └── lib/
│       └── api.ts           # Typed API client
│
├── config/
│   ├── topics/              # ONE FILE PER TOPIC. bootstrapped on app start.
│   │   ├── astronomy-foundations.yaml
│   │   ├── ml-foundations.yaml
│   │   ├── transient-photometric-classification.yaml
│   │   ├── multimodal-foundation-models-astronomy.yaml
│   │   ├── missing-modality-learning.yaml
│   │   ├── generative-cross-modal-imputation.yaml
│   │   ├── sim-to-real-transfer-astronomy.yaml
│   │   └── _archive/        # files here are NOT auto-loaded
│   │       └── generic-ml.yaml   # restore point for old broad-ML behavior
│   └── _archive/
│       ├── interests.yaml.bak   # original pre-unified interests (reference only)
│       └── courses.yaml.bak     # original pre-unified courses (reference only)
│
├── scripts/
│   └── setup_db.py          # Database initialization
│
├── docs/
│   └── LEARNING_GUIDE.md    # Explains each component for learning
│
├── data/                    # SQLite database (auto-generated)
│   └── daily_scholar.db
│
└── uploads/                 # Uploaded course materials
    └── course_materials/
        ├── data-engineering/
        │   └── textbooks/
        └── dl-nlp/
            └── textbooks/
```

---

## Run Locally

The local-mode path is SQLite + local filesystem + local frontend. No Railway, Cloudflare, or Backblaze required. Three commands get you from a fresh clone to a running app.

### Prerequisites

- **Python 3.10+** (`python3 --version`) — 3.13 recommended; 3.10 is the floor because the codebase uses PEP 604 union syntax (`int | None`).
- **Node.js 18+** (`node --version`) — only required if you want the frontend; `--backend-only` mode skips it.
- **An Anthropic API key** at https://console.anthropic.com/ (free tier works for development).

### Quick start

```bash
git clone https://github.com/graciecakes4/daily-scholar.git
cd daily-scholar
make setup                           # venv, deps, .env, migrations, frontend install
nano .env                            # paste your ANTHROPIC_API_KEY
make start                           # backend + frontend, waits for /health, opens up
```

That's it. The dashboard is at http://localhost:3000.

### What `make setup` did

| Step | Effect |
|---|---|
| `python3 -m venv venv` | created the virtualenv (skipped if present) |
| `pip install -r requirements.txt` | installed FastAPI, SQLAlchemy, Alembic, Anthropic SDK, pyjwt, etc. |
| `cp .env.example .env` | created a local config file (skipped if present) |
| `alembic upgrade head` | created `data/daily_scholar.db` and applied every migration |
| `cd frontend && npm install` | installed Next.js 16, React, Tailwind, `@serwist/next` |

Re-running `make setup` is safe — every step is idempotent.

### What `make start` did

`start.sh` launches `uvicorn` on `:8000` and `npm run dev` on `:3000`, then polls `http://127.0.0.1:8000/health` until the backend responds 200 (30s timeout). Once both are up, you see:

```
✅ Daily Scholar is running:
   - App:        http://127.0.0.1:3000
   - API:        http://127.0.0.1:8000
   - API docs:   http://127.0.0.1:8000/docs
   - Health:     http://127.0.0.1:8000/health
```

Press `Ctrl-C` once to stop both processes cleanly.

### Make targets

```
make help        # list every target
make setup       # one-shot setup (idempotent)
make start       # backend + frontend with health check
make backend     # backend only (no frontend)
make test        # run the pytest suite
make migrate     # apply pending alembic migrations
make vapid       # generate VAPID keypair for Web Push (one-time)
make clean       # kill rogue processes on :8000 / :3000
```

If `make` isn't your thing, `./setup.sh` and `./start.sh` do the same work directly. Both scripts accept `--help`.

### Configure your topics

The default topic set ships under `config/topics/examples/` (an astronomy-foundations topic, an ML-foundations topic, and a broad ML/LLM demo). Add your own under `config/topics/examples/` to share, or under `config/topics/private/` to keep them out of git. To switch focus or add a new stream, see [docs/topics.md](docs/topics.md). You can edit YAMLs directly OR use the in-app editor at `http://localhost:3000/topics` — both paths are documented there.

### Daily usage

1. Open http://localhost:3000.
2. View today's content — paper summary, topic review, quiz.
3. Submit quiz answers, archive papers you want to read later, mark topics complete.
4. Explore the API at http://localhost:8000/docs.

### Optional: Web Push notifications

Local-mode supports Web Push for "today's paper is ready" notifications. One-time setup:

```bash
make vapid                           # generates VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT
# paste the three printed lines into .env, then restart with make start
```

Then enable notifications in the app at `/settings/scope`. Regenerating the keypair invalidates every active browser subscription — treat the keys like an API secret.

### Troubleshooting local mode

| Symptom | Fix |
|---|---|
| `setup.sh` fails on `pip install` | confirm `python3 --version` is 3.10+; older versions reject the PEP 604 syntax in `requirements.txt` |
| Backend won't start, says `ANTHROPIC_API_KEY` not set | edit `.env` to add your key |
| `make start` times out on `/health` | check the uvicorn output above the timeout — usually a missing env value or a port-3000/8000 collision (run `make clean`) |
| "table seen_papers already exists" on `alembic upgrade head` | you have a pre-Alembic DB; just run `make start` once and the backend's smart detection handles it |
| Frontend builds but won't hot-reload | confirm `node --version` is 18+; older Node breaks Next.js 16's Turbopack |

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/config/status` | Configuration status (topic-table-backed) |
| `GET` | `/daily` | Today's paper + review + quiz, scoped to active topics |
| `GET` | `/papers/discover` | Discover new papers from the active topic scope |
| `GET` | `/papers/daily` | Today's selected paper |
| `GET` | `/topics` | List all topics (`?stream=`, `?active=`, `?include_orphaned=` filters) |
| `GET` | `/topics/streams` | Distinct stream tags in use |
| `GET` | `/topics/{id}` | Topic detail |
| `POST` | `/topics` | Create a new topic (UI path) |
| `PUT` | `/topics/{id}` | Partial update of a topic |
| `DELETE` | `/topics/{id}` | Soft-delete (`?hard=true` for permanent delete) |
| `POST` | `/topics/import-yaml` | Overwrite DB topics with YAML contents |
| `POST` | `/topics/export-yaml` | Write current DB state out to `config/topics/*.yaml` |
| `GET` | `/topics/{id}/review` | Generate a topic review |
| `GET` | `/topics/random-review` | Generate a review for one topic chosen from active scope |
| `GET` | `/topics/status-summary` | Counts of active / completed / review_later topics |
| `PUT` | `/topics/{id}/status` | Set lifecycle status (`active` / `completed` / `review_later`) |
| `GET` | `/quiz/generate/{id}` | Generate a quiz for a topic |
| `POST` | `/quiz/regenerate` | Multi-topic quiz drawing from active scope |
| `POST` | `/quiz/answer` | Submit quiz answer for evaluation |
| `GET` | `/user/scope` | Current user's topic scope (silo / multi / all) |
| `PUT` | `/user/scope` | Update the topic scope |

### Example API Calls

```bash
# Health check
curl http://localhost:8000/health

# Get configuration status
curl http://localhost:8000/config/status

# Get today's content (paper + reviews + quiz)
curl http://localhost:8000/daily

# Discover papers matching your interests
curl http://localhost:8000/papers/discover

# Get all topics
curl http://localhost:8000/topics

# Generate a quiz for the ml-foundations topic
curl http://localhost:8000/quiz/generate/ml-foundations

# Silo on a single topic
curl -X PUT http://localhost:8000/user/scope \
  -H "Content-Type: application/json" \
  -d '{"scope_mode": "silo", "scope_topic_ids": ["transient-photometric-classification"]}'
```

---

## Configuration

### The unified Topic model

Daily Scholar drives both paper discovery and learning content from a single first-class **Topic** entity. One YAML per topic under `config/topics/` is the bootstrap source; the DB is canonical at runtime. Edits flow either direction via `POST /topics/import-yaml` and `POST /topics/export-yaml`, and there's an in-app editor at `/topics`.

For the full reference — schema, YAML examples, the import/export round trip, scope (silo / multi / all), and a step-by-step for authoring a new stream — see **[docs/topics.md](docs/topics.md)**.

---

## Install as a PWA

Daily Scholar ships as a Progressive Web App: install it on your phone, tablet, or desktop and it behaves like a native app — its own window, a home-screen icon, offline access to recently visited pages.

### Install paths by platform

| Platform | How to install | Notes |
|---|---|---|
| **iOS Safari** | Share button → **Add to Home Screen** | Required step for iOS; the in-app banner explains it the first time. iOS won't fire a native install prompt. |
| **macOS Safari** | File → **Add to Dock** | Safari 17+. |
| **macOS / Windows / Linux Chrome / Edge** | Address-bar install icon, or in-app **Install** button | The Install banner appears automatically on capable browsers. |
| **Android Chrome** | In-app **Install** button (or browser menu → Install app) | Native install prompt fires after the first visit. |

### What works offline

Once installed, the service worker caches:

- The **app shell** (HTML/CSS/JS) — opens instantly even offline.
- **Recently fetched API responses** (papers, topics, archive, daily content) — 24h NetworkFirst cache, so you see the last fresh data when offline.
- **PDFs** you've already viewed — CacheFirst, kept for 90 days.

Actions you take while offline (saving a paper, marking a topic completed, scope updates) are queued in a **background sync queue** and replay automatically when you're back online.

The dev server (`npm run dev`) skips service-worker registration to keep hot-reload sane. To test the PWA end-to-end, build and serve production:

```bash
cd frontend
npm run build         # builds with webpack (see below)
npm start
# open http://localhost:3000 in Chrome with DevTools → Application → Service Workers
```

> **Why the build uses webpack instead of Turbopack:** Next.js 16 defaults to Turbopack, but `@serwist/next` v9 injects its service-worker build via a webpack plugin and isn't Turbopack-compatible yet (see [serwist/serwist#54](https://github.com/serwist/serwist/issues/54)). The `build` script already passes `--webpack`, so this is invisible to you in normal use — but if you ever want to migrate to Turbopack for the production build, you'll need to swap `@serwist/next` for `@serwist/turbopack` or move to configurator mode. Dev (`npm run dev`) stays on Turbopack with the service worker disabled, so HMR remains fast.

### Push notifications

Daily Scholar can push a notification when a new daily paper is generated. Setup is one-time:

```bash
# 1. Generate a VAPID keypair (do this ONCE; reuse forever)
python scripts/generate_vapid_keys.py

# 2. Paste the three printed lines (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT)
#    into your .env

# 3. Restart the backend so it picks up the new env vars
dsf
```

> **Important:** regenerating the VAPID keypair invalidates every existing browser subscription — clients silently stop receiving pushes until they re-subscribe via the toggle. Treat the keys like an API secret.

#### Enabling notifications in the app

Visit `/settings/scope` and click **Enable notifications** under the Notifications section. The browser will:

1. Ask permission to send notifications.
2. Subscribe to push events with your server's VAPID public key.
3. POST the subscription to the backend (`/push/subscribe`).

After that, every time `/daily` generates a fresh paper (either nightly or via the **New paper** button), all your subscribed devices get a push: *"Today's paper is ready — «title»"*. Tapping it opens (or focuses) the dashboard.

There's a **Send test** button in the same settings section to fire a sanity-check push without waiting for a real paper.

#### Per-platform support

| Platform | Works? | Caveat |
|---|---|---|
| Android Chrome | ✓ | Native install + push, no extra setup |
| Desktop Chrome / Edge / Firefox | ✓ | Pushes arrive whether the browser is open or not |
| macOS Safari 16+ | ✓ | Add the site to the Dock first |
| **iOS Safari 16.4+** | ✓ *with caveat* | Must **Add to Home Screen first** — iOS only delivers pushes to installed PWAs. The settings page shows an amber hint if it detects you haven't yet. |

#### Adding more trigger points (future)

The push fanout helper is `backend/services/push_sender.py`. Anywhere in the backend can call:

```python
from .services.push_sender import send_push_to_user
send_push_to_user(user_id, {"title": "...", "body": "...", "url": "/topics/foo"})
```

Examples of where you might wire it next: a daily "topics due for review" digest from APScheduler, a notification when an LLM-generated quiz is ready, or a streak-reminder.

## Hosted version

Everything below this point is for running Daily Scholar as a public PWA on Railway + Cloudflare + Backblaze B2 — Grace's production setup. Beta testers running their own local clone can skip to [Tech Stack](#tech-stack); none of this applies in local mode.

### Migrations + dialect compatibility (CI)

`.github/workflows/test-migrations.yml` runs on every PR to develop or main. Two matrix jobs (SQLite and Postgres) each:

1. Install deps
2. `alembic upgrade head` from scratch
3. `python scripts/check_dialect_compat.py` — exercises JSON columns, the composite-unique constraint on `daily_content_cache`, the unique-per-user constraint on `user_stats`, ArchivedQuiz round-trips
4. `alembic downgrade base && alembic upgrade head` — proves the migration is reversible

To run the compat check locally against whatever DB you're currently pointed at:

```bash
# against SQLite
DATABASE_URL=sqlite:///./data/test.db python scripts/check_dialect_compat.py

# against the compose-managed Postgres
DATABASE_URL='postgresql+psycopg://scholar:scholar@localhost:5432/daily_scholar' \
  python scripts/check_dialect_compat.py
```

Fast feedback loop for catching dialect surprises (unique-constraint syntax, JSON serialization, NULL semantics) before they blow up on Railway.

### Deploy to Railway + Cloudflare

End-to-end deploy of the production stack with a **dev + prod environment split** that maps to your branching strategy:

| Git branch | Railway env | Cloudflare hostname (example) | When it deploys |
|---|---|---|---|
| `develop` | `dev` | `scholar-dev.yourdomain.com` | every push to `develop` |
| `main` | `prod` | `scholar.yourdomain.com` | every push to `main` (after dev validates) |

**Stack:** Railway (backend + frontend + Postgres × 2 environments), Cloudflare (DNS + TLS + Access for auth), Backblaze B2 (PDF storage).

#### One-time provisioning

1. **Railway project + environments**
   - https://railway.app → New Project → Deploy from GitHub repo: `daily-scholar`
   - The project is created with a default environment called `production`. Rename it to `prod` (Settings → rename) and add a second environment called `dev` (Environments → New).
   - **In each environment**, add three things:
     - Backend service from repo root (uses `railway.toml` + `Dockerfile`)
     - Frontend service from `frontend/` (uses `frontend/railway.toml` + `frontend/Dockerfile`)
     - Postgres plugin attached to the backend service
   - Tip: you can clone the dev env's service config to prod after you've validated dev, instead of setting both up by hand twice.
   - For each environment's backend, paste env vars (skip `DATABASE_URL` — auto-injected; skip `FRONTEND_URL` — set to that env's CF hostname):
     - **Same in both**: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `CLAUDE_MODEL`, `LLM_TASK_*`, `STORAGE_BACKEND`, `B2_*`
     - **DIFFERENT in each**: `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` — regenerate a separate keypair for dev so push subscriptions don't cross-pollinate between envs (a device subscribed in dev would otherwise receive prod's pushes too). `FRONTEND_URL` matches the env's CF hostname.
   - Note each service's public hostname under Settings → Networking (`*.up.railway.app`).

2. **Cloudflare DNS + Access (two apps, one per env)**
   - Follow [docs/DEPLOY_CLOUDFLARE.md](docs/DEPLOY_CLOUDFLARE.md). For the dev/prod split you'll create two pairs of CNAMEs (one pair per env) and two Access apps:
     - **Dev**: `scholar-dev` + `api.scholar-dev` → dev Railway services; Access policy = just your email
     - **Prod**: `scholar` + `api.scholar` → prod Railway services; Access policy = you + beta cohort
   - On each backend service, set `FRONTEND_URL` to that env's frontend CF hostname so CORS allows the right origin.

3. **GitHub Actions secrets** (Repo → Settings → Secrets and variables → Actions):

   | Secret | What |
   |---|---|
   | `RAILWAY_TOKEN` | https://railway.app/account/tokens (one token covers both envs) |
   | `RAILWAY_BACKEND_SERVICE_ID_DEV` | from the Railway dashboard URL when viewing the dev-env backend service |
   | `RAILWAY_FRONTEND_SERVICE_ID_DEV` | same, dev frontend |
   | `RAILWAY_BACKEND_SERVICE_ID_PROD` | prod backend |
   | `RAILWAY_FRONTEND_SERVICE_ID_PROD` | prod frontend |

   Optional: under repo Settings → Environments, create `development` and `production` GitHub environments. Give `production` a required reviewer (yourself) if you want every prod deploy to require a manual click in the Actions tab.

4. **First push**

   ```bash
   # ship your in-progress work to dev
   git push origin develop

   # later, when it's ready for prod
   git checkout main && git merge develop && git push origin main
   ```

   The deploy workflow auto-picks the right environment based on which branch you pushed. The migration + dialect-compat gate runs first; if it fails, no deploy happens.

   Tail at https://github.com/{user}/daily-scholar/actions.

#### What runs where

| Component | Hosted on | Domain |
|---|---|---|
| Frontend (Next.js standalone) | Railway | `https://scholar.yourdomain.com` |
| Backend (FastAPI + uvicorn) | Railway | `https://api.scholar.yourdomain.com` |
| Postgres | Railway plugin | (private network only) |
| PDF + upload storage | Backblaze B2 (`STORAGE_BACKEND=b2`) | presigned URLs through CF |
| Auth | Cloudflare Access (Zero Trust free tier) | injects `Cf-Access-Authenticated-User-Email` header |
| Web Push | self-signed VAPID, fanout from `push_sender.py` | direct to browser push endpoints |

#### Cost guardrails

- **Anthropic / Gemini** — set hard monthly caps in each console (Anthropic: https://console.anthropic.com/settings/billing). Expected single-user spend is under $10/mo with the default routing.
- **Railway** — Settings → Usage limits → set a $-per-month cap. Free Trial is generous; expect $5–10/mo for the always-on backend + frontend + 1GB Postgres.
- **Backblaze B2** — first 10 GB free. Egress costs $0 when paired through Cloudflare via the bandwidth alliance.
- **Cloudflare** — DNS, TLS, Access (up to 50 users), Workers (within free tier) are all $0.

#### Rollback

Railway keeps every previous build. Dashboard → Service → Deployments → click any prior deploy → Redeploy. Migrations only move forward by design; if you need to roll back a schema change, do `alembic downgrade -1` locally first, then redeploy with the older revision pinned.

### Docker / docker-compose

Daily Scholar ships with a containerized stack that mirrors what runs on Railway:

```bash
docker compose up --build
# postgres on :5432, backend on :8000, frontend on :3000
# Ctrl-C to stop; `docker compose down -v` to also nuke volumes
```

Three services:

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:17-alpine` | Volume-backed at `pgdata`. Healthcheck via `pg_isready`. |
| `backend` | built from `./Dockerfile` (Python 3.13-slim, multi-stage) | Starts only after postgres passes healthcheck. Reads `.env` for secrets, but `DATABASE_URL` is overridden to point at the compose-managed Postgres. |
| `frontend` | built from `./frontend/Dockerfile` (Next.js standalone) | Starts only after backend healthcheck passes. |

#### Switching between SQLite and Postgres locally

The compose stack defaults to Postgres. To force-switch the *non-compose* dev flow (running `uvicorn backend.main:app --reload` directly), unset or rewrite `DATABASE_URL`:

```bash
# SQLite — what beta testers use
unset DATABASE_URL
# or in .env: DATABASE_URL=sqlite:///./data/daily_scholar.db

# Postgres against the compose stack while running uvicorn natively
export DATABASE_URL='postgresql+psycopg://scholar:scholar@localhost:5432/daily_scholar'
```

Alembic migrations apply automatically on startup via `create_tables()` regardless of which backend is selected.

#### Persistent volumes

- `pgdata` — Postgres data files
- `backend_data` — mounted at `/app/data` (SQLite db fallback + LocalStorage PDFs when `STORAGE_BACKEND=local`)
- `backend_uploads` — mounted at `/app/uploads` (course materials)

`config/topics` is bind-mounted **read-only** into the backend so you can edit topic YAMLs from your editor and call `POST /topics/import-yaml` to pick them up without rebuilding the image.

#### A note on the frontend build

The frontend Dockerfile passes `--webpack` to `next build` so `@serwist/next` (the PWA service-worker plugin) can run — it doesn't support Turbopack yet. This matches what `dsbpwa` does for native builds. See the "Install as a PWA" section for the full story.

### Scheduled jobs + deep health check

A background scheduler runs nightly to regenerate the daily content (paper + topic review + quiz) and fire the "today's paper is ready" push notification. The scheduler starts automatically with the backend, runs in-process via APScheduler's AsyncIO loop, and reuses the exact same code path as the `New paper` button — no HTTP round-trips, no duplicated logic.

Configure via env:

```bash
DAILY_GENERATION_TIME=06:00        # 24h HH:MM in the timezone below
TIMEZONE=America/New_York          # IANA tz name; defaults to UTC if empty
SCHEDULER_DISABLED=                # set to "1" to skip starting the scheduler (tests, CI)
```

Inspect at runtime:

```bash
curl http://localhost:8000/admin/scheduler/jobs
# [{"id": "nightly-daily-content", "next_run_time": "2026-06-17T06:00:00-04:00", ...}]

# fire a job manually instead of waiting for the cron tick
curl -X POST http://localhost:8000/admin/scheduler/run/nightly-daily-content
```

#### `/health/deep`

Two health endpoints with different scopes:

| Endpoint | Purpose | Use it for |
|---|---|---|
| `GET /health` | Lightweight: env config + active topic count | Railway / Cloudflare / load-balancer health probes |
| `GET /health/deep` | Per-subsystem ping (DB, LLM keys, storage, push, arXiv, scheduler) with latency | On-call debugging, dashboards, "what's down" |

`/health/deep` returns 200 only when **db** and **llm.anthropic** both pass (the critical set). Storage / push / Gemini / arXiv failures show as ✗ in the response but don't push the overall status to 503 — informational. Example response:

```json
{
  "status": "healthy",
  "timestamp": "2026-06-16",
  "subsystems": {
    "db":             { "ok": true,  "latency_ms": 0.4, "url_scheme": "sqlite" },
    "llm.anthropic":  { "ok": true,  "latency_ms": 0.0, "model": "claude-sonnet-4-5" },
    "llm.gemini":     { "ok": true,  "latency_ms": 0.0, "configured": true },
    "storage":        { "ok": true,  "latency_ms": 1.2, "backend": "local" },
    "push.vapid":     { "ok": true,  "latency_ms": 0.0, "configured": true },
    "arxiv":          { "ok": true,  "latency_ms": 142.0, "status_code": 200 },
    "scheduler":      { "ok": true,  "latency_ms": 0.0, "running": true, "job_count": 1 }
  }
}
```

### Storage backend (PDFs + uploads)

File writes (paper PDFs, uploaded course materials) go through a single `Storage` abstraction with two adapters:

| Backend | When | Setup |
|---|---|---|
| **local** (default) | Beta testers, development, anyone running solo | Files land under `LOCAL_STORAGE_ROOT` (default `./data`). No extra setup. |
| **b2** | Hosted deployment | Files land in a Backblaze B2 bucket via S3-compatible API. Browser downloads use time-limited presigned URLs so the backend stays out of the bytes path. |

Switch at runtime via env:

```bash
STORAGE_BACKEND=b2
B2_ENDPOINT_URL=https://s3.us-west-002.backblazeb2.com
B2_KEY_ID=...
B2_APPLICATION_KEY=...
B2_BUCKET_NAME=daily-scholar
B2_REGION=us-west-002
```

Get B2 keys at https://secure.backblaze.com/app_keys.htm — scope them to the bucket you create.

**Cost tip:** if you put the B2 bucket behind a Cloudflare custom hostname, Backblaze and Cloudflare have a zero-egress agreement, so PDF downloads cost $0 in B2 egress fees. Presigned URLs work fine through CF as long as the bucket allows it. Worth doing before you point real traffic at it.

**Legacy data:** PDFs uploaded before this refactor are stored at `./data/papers/<uuid>.pdf` with that absolute path saved in the DB. The endpoint normalizes the legacy form into a storage key on read, so existing PDFs keep working without a data migration. New writes use the key form directly.

### Multi-provider LLM routing

Daily Scholar splits each LLM call site into a named *task* and routes each task independently to a provider+model:

| Task | What it powers | Default routing | Why |
|---|---|---|---|
| `summary` | Paper summaries on the dashboard | `anthropic:claude-haiku-4-5` | Cheap distillation; doesn't need premium reasoning |
| `review` | Topic-review study notes | `anthropic:claude-sonnet-4-5` | Needs structured pedagogical reasoning |
| `quiz` | Multi-question quiz generation | `anthropic:claude-sonnet-4-5` | Question construction must be careful and unambiguous |
| `evaluate` | Open-answer scoring | `anthropic:claude-haiku-4-5` | Simple correctness check |
| `default` | Fallback for anything new | `anthropic:claude-sonnet-4-5` | Sensible middle ground |

Supported providers: **anthropic**, **gemini**, **antigravity**. Defaults live in `backend/services/llm/factory.py` (`DEFAULT_TASK_ROUTING`). Override any one via env var without touching code:

```bash
# in .env — format is "provider:model"
LLM_TASK_SUMMARY=gemini:gemini-2.5-flash     # send summaries to Gemini
LLM_TASK_QUIZ=antigravity:gemini-2.5-pro     # route quiz generation through the Antigravity agent
LLM_TASK_REVIEW=anthropic:claude-opus-4-8    # use a more capable Claude model for reviews
```

To enable a Google provider, set:

```bash
GEMINI_API_KEY=...               # get one at https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash    # fallback for gemini: routes with no explicit model
ANTIGRAVITY_MODEL=               # leave blank to use the Antigravity SDK default
```

The `google-genai` and `google-antigravity` SDKs are only imported when a task is actually routed to one of them, so you can run with only `ANTHROPIC_API_KEY` set if you stick to Anthropic.

**A note on Antigravity:** it's Google's agent-native platform — stateful sessions, managed execution, tool use. Under the hood every call is still a Gemini call, plus agent-setup overhead. Reach for `antigravity:` when you want the agent harness (e.g., to add tool calls or persistent sessions later); for raw single-turn throughput, `gemini:` is faster.

### Swapping the app icon

Icons live in `frontend/public/icons/`. The placeholder set (book-on-slate) was generated; replace any of `icon-{192,256,384,512}.png` and the matching `*-maskable.png` to rebrand. Required sizes are referenced in `public/manifest.json` and `app/layout.tsx`.

For a one-shot regenerate from a single 512×512 source image:

```bash
python3 -c "
from PIL import Image
src = Image.open('frontend/public/icons/source.png')
for s in (192, 256, 384, 512):
    src.resize((s, s), Image.LANCZOS).save(f'frontend/public/icons/icon-{s}.png', 'PNG', optimize=True)
"
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python 3.10+ (3.13 recommended) | Core language |
| | FastAPI | Web framework |
| | SQLite | Database |
| | Pydantic | Data validation |
| | httpx | HTTP client |
| **Frontend** | Next.js 16+ | React framework |
| | TypeScript | Type safety |
| | Tailwind CSS | Styling |
| | @serwist/next | PWA service worker (Workbox-based) |
| **APIs** | Anthropic Claude | Content generation (default for all tasks) |
| | Google Gemini | Content generation (optional, per-task routing) |
| | Google Antigravity | Content generation via agent harness (optional, per-task routing) |
| | arXiv | Paper discovery |
| | Semantic Scholar | Paper metadata |

---

## Learning Path

This project is designed to help you learn:

| Week | Focus | Activities |
|------|-------|------------|
| 1-2 | Understand | Run the system, explore API docs, read code |
| 3-4 | Modify | Edit configurations, adjust interests/courses |
| 5-6 | Extend | Add new features, customize quiz types |
| 7-8 | Build | Create new frontend components |
| Ongoing | Own | Full ownership - add whatever you want! |

See `docs/LEARNING_GUIDE.md` for detailed explanations.

---

## Troubleshooting

### Backend won't start

**Error:** `ImportError: attempted relative import with no known parent package`

**Solution:** Run from project root, not from inside `backend/`:
```bash
cd ~/daily-scholar           # ✅ Correct
uvicorn backend.main:app --reload

# NOT:
cd ~/daily-scholar/backend   # ❌ Wrong
uvicorn main:app --reload
```

### Frontend is slow to compile

**Cause:** Project is in a cloud-synced folder (OneDrive, Dropbox, iCloud)

**Solution:** Move project to a local directory:
```bash
cp -r /path/to/cloud/daily-scholar ~/daily-scholar
cd ~/daily-scholar/frontend
rm -rf node_modules .next
npm install
npm run dev
```

### CSS parsing error with @import

**Error:** `@import rules must precede all rules`

**Solution:** Move any `@import` statements to the very top of `frontend/app/globals.css`

### python command not found

**Solution:** Use `python3` instead:
```bash
python3 -m venv venv
python3 scripts/setup_db.py
```

### npm command not found

**Solution:** Install Node.js:
```bash
brew install node  # macOS with Homebrew
# Or download from https://nodejs.org/
```

### API returns null for papers

**Cause:** Network issues, restrictive topic scope, or no matching papers

**Solution:**
1. Check your internet connection
2. Try `GET /papers/discover` directly in Swagger UI
3. Broaden the active topic scope at `/settings/scope` (e.g., switch from `silo` to `all`)
4. Add keywords to the relevant topic at `/topics/{id}/edit`, or lower its `min_relevance`

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is for personal educational use.
