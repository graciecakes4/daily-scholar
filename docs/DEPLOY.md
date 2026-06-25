# Hosted Deploy — Railway + Cloudflare + Backblaze B2

Turn your fork into a hosted PWA: install on your phone, push notifications, data syncing across devices. If you're happy running locally, you can skip this entire doc — the local-mode path described in the [README](../README.md) doesn't require any of this.

## Architecture at the deploy boundary

| Component | Hosted on | Domain |
|---|---|---|
| Frontend (Next.js standalone) | Railway | `https://scholar.yourdomain.com` |
| Backend (FastAPI + uvicorn) | Railway | `https://api.scholar.yourdomain.com` |
| Postgres | Railway plugin | (private network only) |
| PDF + upload storage | Backblaze B2 (`STORAGE_BACKEND=b2`) | presigned URLs through CF |
| Auth | Cloudflare Access (Zero Trust free tier) | injects `Cf-Access-Authenticated-User-Email` header |
| Web Push | self-signed VAPID, fanout from `push_sender.py` | direct to browser push endpoints |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system diagram.

## Migrations + dialect compatibility (CI)

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

## Deploy to Railway + Cloudflare

End-to-end deploy of the production stack with a **dev + prod environment split** that maps to your branching strategy:

| Git branch | Railway env | Cloudflare hostname (example) | When it deploys |
|---|---|---|---|
| `develop` | `dev` | `scholar-dev.yourdomain.com` | every push to `develop` |
| `main` | `prod` | `scholar.yourdomain.com` | every push to `main` (after dev validates) |

### One-time provisioning

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
   - Follow [DEPLOY_CLOUDFLARE.md](DEPLOY_CLOUDFLARE.md). For the dev/prod split you'll create two pairs of CNAMEs (one pair per env) and two Access apps:
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

### Cost guardrails

- **Anthropic / Gemini** — set hard monthly caps in each console (Anthropic: https://console.anthropic.com/settings/billing). Expected single-user spend is under $10/mo with the default routing.
- **Railway** — Settings → Usage limits → set a $-per-month cap. Free Trial is generous; expect $5–10/mo for the always-on backend + frontend + 1GB Postgres.
- **Backblaze B2** — first 10 GB free. Egress costs $0 when paired through Cloudflare via the bandwidth alliance.
- **Cloudflare** — DNS, TLS, Access (up to 50 users), Workers (within free tier) are all $0.

### Rollback

Railway keeps every previous build. Dashboard → Service → Deployments → click any prior deploy → Redeploy. Migrations only move forward by design; if you need to roll back a schema change, do `alembic downgrade -1` locally first, then redeploy with the older revision pinned.

## Docker / docker-compose

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

### Switching between SQLite and Postgres locally

The compose stack defaults to Postgres. To force-switch the *non-compose* dev flow (running `uvicorn backend.main:app --reload` directly), unset or rewrite `DATABASE_URL`:

```bash
# SQLite — the local-mode default
unset DATABASE_URL
# or in .env: DATABASE_URL=sqlite:///./data/daily_scholar.db

# Postgres against the compose stack while running uvicorn natively
export DATABASE_URL='postgresql+psycopg://scholar:scholar@localhost:5432/daily_scholar'
```

Alembic migrations apply automatically on startup via `create_tables()` regardless of which backend is selected.

### Persistent volumes

- `pgdata` — Postgres data files
- `backend_data` — mounted at `/app/data` (SQLite db fallback + LocalStorage PDFs when `STORAGE_BACKEND=local`)
- `backend_uploads` — mounted at `/app/uploads` (course materials)

`config/topics` is bind-mounted **read-only** into the backend so you can edit topic YAMLs from your editor and call `POST /topics/import-yaml` to pick them up without rebuilding the image.

### A note on the frontend build

The frontend Dockerfile passes `--webpack` to `next build` so `@serwist/next` (the PWA service-worker plugin) can run — Serwist v9 doesn't support Turbopack yet. The `dev` script in `frontend/package.json` also pins `--webpack` for the same reason. See [PWA.md](PWA.md) for the full story.

## Scheduled jobs + deep health check

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

### `/health/deep`

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

## Storage backend (PDFs + uploads)

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

**Legacy data:** PDFs uploaded before the storage refactor are stored at `./data/papers/<uuid>.pdf` with that absolute path saved in the DB. The endpoint normalizes the legacy form into a storage key on read, so existing PDFs keep working without a data migration. New writes use the key form directly.

## Multi-provider LLM routing

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
