# Daily Scholar → Praxis-Aligned PWA: Migration Plan (v2)

**Drafted:** 2026-06-15 · **Revised:** 2026-06-15 after first-round answers
**Target:** Convert Daily Scholar from a broad LLM/ML local-clone app into a praxis-aligned, cloud-hosted PWA focused on time-domain transient classification, with a unified **Topic** model (replacing today's split between `interests` and `courses`), editable from both YAML and the web UI, and a topic-scope selector for silo / multi-select / aggregate modes. Existing local-clone beta flow is preserved.

**Stack decisions (locked):**
- Backend: Railway (FastAPI + Postgres + APScheduler worker)
- Frontend: Vercel (preferred) or Cloudflare Pages
- Storage: Backblaze B2 via S3-compatible API
- DNS / CDN / TLS: Cloudflare
- LLM: multi-provider (Anthropic + OpenAI + room for one cheap fallback), refactor lands during cloud migration
- Push: Web Push (VAPID) targeting installed PWAs on iOS 16.4+, macOS Safari 16+, Chrome Android, desktop Chrome/Edge/Firefox

---

## 1. Current State (verified against repo)

**Backend** — FastAPI, SQLAlchemy, SQLite (`./data/daily_scholar.db`). ~3,500 LOC across `backend/{main,config,database,models}.py` and `backend/services/{paper_discovery,content_generator}.py`. 30+ endpoints across Papers, Topics, Archive, Quiz, Stats. LLM provider hardcoded to the Anthropic SDK (`anthropic.Anthropic`, `claude-sonnet-4-20250514`). No background worker — paper discovery and LLM calls run synchronously inside request handlers. No Alembic. No Docker.

**Frontend** — Next.js 16, React 18, Tailwind, plain app-router pages (`app/{papers,quiz,topics}/page.tsx` + root). No service worker, no manifest, no PWA infrastructure.

**Config** — `config/interests.yaml` (wide-ranging ML/LLM/CV/RL, zero astronomy) + `config/courses.yaml` (legacy course curriculum, no longer active).

**Schema** — single-user. `UserStats` is one row; no `user_id` columns anywhere. Database tables: `seen_papers`, `archived_papers`, `paper_pdfs`, `archived_topic_reviews`, `archived_quizzes`, `daily_content_cache`, `user_stats`.

**External APIs you already have:** arXiv (no key needed), CORE (Bearer token), Semantic Scholar (optional key). A university-library API is a stretch goal — depends on what's exposed; worth confirming scope before architecting around it.

---

## 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  PWA (Next.js, installable on iOS / macOS / Android / desktop)        │
│  service worker · IndexedDB cache · Web Push subscription            │
└──────────────────────────────────────────────────────────────────────┘
                              │ HTTPS (scholar.<yourdomain>)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Cloudflare  (DNS · TLS · CDN · optional Access for future auth)      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Railway                                                              │
│  ┌────────────────────────┐    ┌────────────────────────────────┐    │
│  │  FastAPI service       │ ──►│  APScheduler (in-process)      │    │
│  │  + Web Push trigger    │    │  nightly paper discovery,      │    │
│  │  + topic CRUD          │    │  LLM generation, push fanout   │    │
│  └─────────┬──────────────┘    └────────────────────────────────┘    │
│            │                                                          │
│            ▼                                                          │
│  ┌────────────────────────┐                                           │
│  │  Railway Postgres      │                                           │
│  │  topics, papers, quiz, │                                           │
│  │  push_subscriptions    │                                           │
│  └────────────────────────┘                                           │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Backblaze B2 (S3-compatible)                                         │
│  PDFs · course-material uploads · LLM artifacts                       │
│  presigned URLs for direct browser download                           │
└──────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ env-switched
┌──────────────────────────────────────────────────────────────────────┐
│  Local beta path (unchanged):                                         │
│  SQLite + local filesystem + start.sh, single Storage abstraction,    │
│  same Topic model, no Web Push, no Postgres requirement.              │
└──────────────────────────────────────────────────────────────────────┘
```

One codebase, two runtime modes selected by env. Beta testers don't need a Railway account, a B2 bucket, or a Cloudflare zone.

---

## 3. The Unified `Topic` Model

This is the biggest conceptual change from v1 of the plan. Today's `interests` (paper discovery) and `courses` (review + quiz) collapse into a single first-class entity.

### 3.1 Topic schema

Each topic — represented both as a YAML file and as a DB row — has:

```yaml
# config/topics/transient-photometric-classification.yaml
id: transient-photometric-classification          # stable slug, used as FK
name: Photometric Transient Classification
stream: photometric_classification                # grouping tag for the UI (Chapter 2 lit streams)
active: true                                      # quick on/off without deletion
weight: 2.0                                       # boosts relevance scoring for discovery

# --- paper discovery side (replaces interests.yaml content) ---
keywords:
  - time-domain
  - transient classification
  - ELAsTiCC
  - light curve
  - ORACLE
  - ATCAT
arxiv_categories: [astro-ph.IM, astro-ph.HE, cs.LG]
recency_days: 30
min_relevance: 0.18

# --- learning-content side (replaces courses.yaml topics) ---
key_concepts:
  - hierarchical 20-class taxonomy
  - photometry-only macro-F1 floor
  - cadence-aware positional encoding
learning_objectives:
  - Reproduce ORACLE photometry-only floor on ELAsTiCC dev set
  - Identify failure modes of photometry-only classifiers on rare classes
resources:
  - astronomy/Transient classifiers for Fink Benchmarks for LSST.pdf
quiz_difficulty: medium
prerequisites: []
```

### 3.2 Sliced files, one topic per file

`config/topics/` holds one file per topic. Starting set for Phase 0:

```
config/topics/
  transient-photometric-classification.yaml
  multimodal-foundation-models-astronomy.yaml
  missing-modality-learning.yaml
  generative-cross-modal-imputation.yaml
  sim-to-real-transfer-astronomy.yaml
  proposal-deliverables.yaml             # tracks proposal-phase milestones
```

Six small files instead of two huge ones. Easier to diff, easier to add new ones, easier to compose. The previous broad `interests.yaml` content is moved to `config/topics/_archive/generic-ml.yaml` (inactive by default) so beta testers who want the old behavior can flip a switch.

### 3.3 DB as source of truth, YAML as bootstrap + export

- **App startup**: scans `config/topics/`, upserts each file into the `topics` table by `id`. If a file is removed, the corresponding DB row is *not* deleted (so UI-only topics aren't blown away) — instead it's marked `source_yaml_present = false`.
- **UI edits**: write to the DB only. Editor surfaces are CRUD on the topic table plus a per-topic edit page covering all fields.
- **YAML export**: a `POST /topics/export-yaml` endpoint writes the current DB state back out as one file per topic. On local-beta machines this updates the working tree so you can `git diff` and commit. On Railway it returns a downloadable archive.
- **Why this way**: cloud filesystems are ephemeral, so UI-write-back-to-YAML is fragile in production. Beta testers who *only* edit YAML still work cleanly because the YAML is the bootstrap path on every cold start.

### 3.4 Topic scope selector

The UI gets a global topic scope selector that controls what Paper Discovery, Topic Review, and Quiz Generation operate on. Three modes:

- **Silo** — single topic, deep focus. Paper search uses only that topic's keywords/categories; reviews and quizzes draw only from it.
- **Multi-select** — explicit set. Useful for "this week I'm in lit-stream A and lit-stream B."
- **All active** — every topic with `active: true`. Default for browsing.

Selection persists per user in `user_settings` (cookie + DB-backed), with quick override on the Discover / Quiz / Review pages. The current "1 paper per day" daily strategy is preserved but the candidate pool follows the active scope.

You're not way off on UI being the right surface for this — YAML would need a separate session-state file or active-set toggle per topic, which conflicts with the YAML-as-declarative-config principle.

---

## 4. Phased Plan

### Phase 0 — Topic-model refactor (3–4 sessions, no infra changes)

Highest-leverage piece, ships independently of everything else, immediately useful for the annotated-bibliography phase of upstream research.

- New `topics` SQLAlchemy model + Alembic migration (introducing Alembic here so we don't have to retrofit later).
- `config/topics/` directory + the six initial topic YAMLs, including the praxis-aligned ones above.
- `_archive/generic-ml.yaml` containing today's interests preserved for fallback.
- Bootstrap loader: scan `config/topics/`, upsert into DB on startup.
- Refactor `paper_discovery.py` to read keywords/categories from the `topics` table filtered by active scope, not from `interests.yaml`.
- Refactor topic-review and quiz endpoints to read from `topics` table, not from `courses.yaml`.
- New endpoints:
  - `GET  /topics` — list (with filter by stream, active flag, scope)
  - `GET  /topics/{id}` — detail
  - `POST /topics` — create
  - `PUT  /topics/{id}` — update
  - `DELETE /topics/{id}` — soft-delete (`active=false`) by default
  - `POST /topics/export-yaml` — dump DB state back to YAML
  - `POST /topics/import-yaml` — manual re-import trigger
  - `GET / PUT /user/scope` — get/set the active topic scope (silo / multi / all)
- New frontend pages:
  - `/topics` — list with stream-grouped UI, active-toggle, delete
  - `/topics/new` and `/topics/[id]/edit` — full editor (name, stream, keywords list, arXiv categories list, key concepts, learning objectives, resources, difficulty, weight, active)
  - `/settings/scope` — scope selector (silo / multi / all)
- Delete `config/interests.yaml` and `config/courses.yaml` after the migration is verified. Keep a copy in git history.

**Exit criteria:** swapping scope between transient-photometric-classification and missing-modality-learning measurably changes the papers Discover surfaces; adding a topic via UI persists across restarts; `POST /topics/export-yaml` produces files matching the DB state.

### Phase 1 — PWA shell + Web Push (3–4 sessions, frontend-heavy)

- Install `@serwist/next` (Workbox-based, supports Next.js 16 app router) — `next-pwa` is largely unmaintained at this point.
- `public/manifest.json` with name, short_name, start_url, display: standalone, theme/background, scope, icons (192/256/384/512 PNG + maskable variants).
- iOS-specific meta tags in `app/layout.tsx`: `apple-touch-icon`, `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`.
- Service worker caching:
  - App shell — precache, stale-while-revalidate.
  - `GET /papers/daily`, `/topics`, `/archive/*` — network-first, 24h cache fallback.
  - PDFs — cache-first.
  - Mutations — background sync queue, replay on reconnect.
- Install prompt: listen for `beforeinstallprompt`; on iOS show a non-modal "Add to Home Screen" instructions card.
- Offline shell route.
- **Web Push (full surface coverage):**
  - Backend: generate VAPID keypair, store in env. New `push_subscriptions` table (`user_id`, `endpoint`, `p256dh`, `auth`, `platform`, `topic_scope_id_optional`, `created_at`). New endpoints `POST /push/subscribe`, `POST /push/unsubscribe`, `POST /push/test`.
  - Trigger points: nightly daily-paper job pushes "Today's paper: «title»" with deep-link; topic-review-due job pushes "X topics ready for review."
  - Frontend: permission flow, subscription persistence, per-platform UX. On iOS 16.4+, only works after the user adds to home screen — show a one-time card explaining the constraint when they hit Settings → Notifications before installing.
  - Library: `pywebpush` server-side, no library needed client-side (use Push API + Notification API directly via the service worker).
- Lighthouse PWA audit; clean PWA badge before Phase 2.

**Exit criteria:** installs on iPhone (Safari → Share → Add to Home Screen), macOS desktop (Chrome PWA install), Android Chrome (native install prompt). Push notification received on all three when the nightly job fires. App shell loads offline.

### Phase 2 — Backend cloudification + multi-provider LLM (4–5 sessions)

- **Containerize.** Backend Dockerfile (Python 3.12-slim, multi-stage). `docker-compose.yml` for local parity (Postgres + backend + frontend).
- **SQLite → Postgres compat pass.** Verify JSON columns use SQLAlchemy `JSON` (Postgres `jsonb`). Run migrations against both backends in CI.
- **Background worker.** APScheduler in-process via a FastAPI lifespan hook. Jobs: nightly paper discovery (per topic scope), nightly LLM generation, push fanout, daily content cache cleanup. Defer Dramatiq/Redis until horizontal scaling is needed.
- **Storage abstraction.** `backend/services/storage.py` with two adapters:
  - `LocalStorage` — writes to `./uploads/` (beta path).
  - `B2Storage` — boto3 against B2 S3-compatible endpoint. PDFs, uploads, LLM artifacts. Pre-signed URLs for browser-direct downloads to keep your backend out of the bytes path.
  - Env switches: `STORAGE_BACKEND=local|b2`, `B2_ENDPOINT_URL`, `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`, `B2_REGION` (e.g., `us-west-002`).
- **Multi-provider LLM.** New `backend/services/llm/` package:
  - `interface.py` defines `LLMClient` with `complete`, `complete_json`, `embed` methods.
  - `anthropic_client.py`, `openai_client.py`, plus a `LocalFallbackClient` stub for future cheap model.
  - `factory.py` returns the configured client per task. Per-task model selection (paper summaries use cheap; quiz generation uses premium).
  - Per-topic override possible: `topic.llm_overrides = {summary: openai/gpt-4o-mini, quiz: anthropic/claude-sonnet}` for cost-aware routing.
  - Env: `LLM_PRIMARY_PROVIDER`, `LLM_SECONDARY_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
- **Secrets** via Railway's env-var UI. `.env.example` documents the full set. The committed `.env` (currently in the repo per `ls -la`) gets removed and added to `.gitignore` if it isn't already.
- **Health endpoints.** Keep `/health` lightweight for Railway's check. Add `/health/deep` that pings DB + each LLM provider + arXiv + B2 head-bucket.

**Exit criteria:** `docker compose up` boots the full stack locally; backend runs cleanly against Postgres; nightly job runs from APScheduler not a request handler; PDFs land in a B2 bucket; the same backend runs unchanged in SQLite+local-storage mode for beta testers; LLM provider is swappable via env.

### Phase 3 — Cloud deploy via Railway + Cloudflare (1–2 sessions)

- **Backend on Railway.** Provision: 1 web service (Dockerfile build), 1 Postgres add-on. The APScheduler worker rides inside the web service for now; if scaling out, split into a second service. Configure: env vars (LLM keys, B2 creds, VAPID keys, `DATABASE_URL` from Railway plug-in), domain.
- **Frontend.** Recommend **Vercel** for Next.js 16 app-router maturity and built-in PWA-friendliness. If single-vendor matters more than smoothness, **Cloudflare Pages** (their Next.js app-router support is good as of 2026 but you'll hit edges around streaming and middleware). I'd ship Vercel first and switch later if needed.
- **DNS + TLS via Cloudflare.** Subdomain `scholar.<yourdomain>` → CNAME to Railway (backend) or Vercel (frontend). Cloudflare-issued cert. Proxy mode "on" so Cloudflare handles WAF + caching + analytics.
- **CI/CD.** Your existing GitHub Actions with Claude Code review stays in place. Add `.github/workflows/deploy.yml` that runs Alembic migrations and triggers `railway up` on `main`. Frontend autodeploys from Vercel's GitHub integration.
- **Auth-readiness via Cloudflare Access.** Worth highlighting: rather than building auth into the app, you can put the PWA behind **Cloudflare Access** (Zero Trust). Free tier supports up to 50 users with email-based identity (one-time-PIN or Google/GitHub SSO). Beta testers later become "add their email to the Access policy" — no schema changes, no auth UI, no password management. We still add nullable `user_id` columns (cheap insurance) but with Access in front you may never need the in-app auth UI.
- **Cost ceilings.** Hard caps in Anthropic / OpenAI dashboards. Railway free trial is generous; expect ~$5–10/mo at praxis scale. B2 storage is essentially free at this volume. Cloudflare is free for this use case.

**Exit criteria:** `scholar.<yourdomain>` resolves, serves the PWA over HTTPS, installs on your phone, nightly paper job fires and triggers a push. Pushing to `main` deploys.

### Phase 4 — Auth-readiness (deferred, ~0.5 session of schema work in Phase 2)

Two parallel tracks of "auth readiness":

- **Schema (now):** add nullable `user_id` columns (default `'__local__'`) to `seen_papers`, `archived_papers`, `archived_quizzes`, `archived_topic_reviews`, `paper_pdfs`, `daily_content_cache`, `user_stats`, `push_subscriptions`, `user_settings`. Index appropriately. Every endpoint filters by current user. Behavior unchanged for solo + beta.
- **Identity (deferred):** Cloudflare Access is the recommended path for hosted multi-user; the in-app `get_current_user` dependency reads the `Cf-Access-Jwt-Assertion` header when present, falls back to the sentinel otherwise. No UI work to flip on real auth — just a Cloudflare Access policy change.

**Exit criteria:** option-3 (multi-user beta on the hosted PWA) becomes a Cloudflare Access policy update plus enabling the JWT-validation middleware. No migration, no UI build.

### Phase 5 — Beta-flow preservation (continuous)

- `setup.sh` / `start.sh` / `Makefile` still bring up SQLite + local filesystem + local frontend with no Railway / B2 / Cloudflare dependency.
- README split: "Run locally (clone & start)" vs "Use the hosted version" (Grace-only initially, beta testers later via Cloudflare Access).
- Topic-model docs: explain YAML editing, UI editing, the import/export endpoints, and how to author a new stream.
- Resolve the open pre-beta items from memory: `start.sh` health check, `v0.1.0-beta` tag, `run_tmux.sh` decision (likely just delete it now that APScheduler runs the background work — `run_tmux.sh` is a remnant of the synchronous-handler era).

---

## 5. Sequencing & Dependencies

```
Phase 0 (topic model) ───► Phase 1 (PWA shell + push) ─┐
                                                       ├──► Phase 3 (Railway + CF deploy)
Phase 2 (cloudify + multi-LLM + B2 + auth schema) ─────┘
Phase 4 (auth identity) — deferred indefinitely, no work until you flip option 3
Phase 5 (beta preservation) — continuous; verified at end of Phase 3
```

Phase 0 is independently shippable; if upstream deadlines crowd everything else out, Phase 0 alone makes Daily Scholar topic-aligned.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Topic model migration breaks beta testers' existing data | Low | High | Migration ships with a data-import script that maps the old `interests.yaml` + `courses.yaml` shape into the new topics table; CI runs the import against a sample of the old configs. |
| `@serwist/next` lags Next.js 16 edge cases | Medium | Low | Pin versions; fall back to a hand-rolled Workbox service worker if needed. |
| iOS 16.4+ Web Push requires Add-to-Home-Screen first | High | Low | Show an explicit pre-permission card explaining the install step; remember dismissals. |
| Web Push on macOS Safari is the most finicky surface | Medium | Low | Treat macOS Safari as "best-effort" and prefer Chrome/Edge PWAs on macOS in docs. |
| Railway free tier exhausts under sustained background work | Low | Medium | Set memory/CPU limits; monitor; move to hobby plan if needed (still ~$5/mo). |
| Backblaze egress fees if PDFs are downloaded repeatedly | Low | Medium | B2 has Cloudflare-egress-free agreement; route PDF downloads through CF for $0 egress. Pre-signed URLs work fine through CF. |
| LLM cost spikes after deploy | Low at 1 user | Medium | Per-task model selection (cheap for summaries, premium for quizzes); hard caps in provider dashboards. |
| Multi-provider LLM refactor introduces regressions in content generation | Medium | Medium | Snapshot a "golden" set of summaries + quizzes from the current Anthropic-only path before refactor; assert byte-near-equivalence on the same prompts post-refactor. |
| Upstream deadlines crowd out app work | High | High | Phase 0 only is shippable. Phases 1–3 are deferred until proposal work lands. |
| `daily scholar` empty subfolder in repo root | Low | Low | Delete — stray mount artifact. |
| Schema drift between SQLite-local and Postgres-cloud | Medium | Medium | Alembic is source of truth from Phase 0 forward; CI runs migrations against both backends on every PR. |
| University-library API never materializes | Medium | Low | Don't architect around it; if it lands, add as a new paper source plugin behind the existing source-plugin interface. |
| Cloudflare Access free tier (50 users) hit during beta | Low | Low | Beta is 30 testers per memory; well under cap. If exceeded, upgrade to Zero Trust paid (~$3/user/mo). |

---

## 7. Recommended sequencing

Phase 0 is the highest-leverage piece and ships independently of everything else. Suggested order, scaled to whatever upstream timeline applies:

1. **Sprint 1:** Phase 0 in full. Daily Scholar starts surfacing on-topic papers immediately, which is the smallest unit of "useful."
2. **Sprint 2 (after Phase 0 stabilizes):** Phase 1 (PWA shell + Web Push). Frontend-heavy, low backend risk.
3. **Sprint 3:** Phase 2 (cloudify + multi-LLM + B2 + auth schema).
4. **Sprint 4:** Phase 3 deploy.
5. **Continuous:** Phase 5 doc maintenance + tying off pre-beta TODOs.

This puts a hosted, push-enabled, topic-tuned PWA on the phone before any downstream consumers need it.

---

## 8. Open Questions Before Phase 0 Starts

1. **YAML loader strictness.** When a topic YAML and the DB disagree (you edited via UI, then someone re-edits the YAML and pushes), which wins? My default: **DB wins after first bootstrap**, YAML changes require an explicit `POST /topics/import-yaml` call to merge. Alternative: YAML always wins on startup (simpler, riskier — UI edits can be silently overwritten).
2. **Topic deletion semantics.** Soft-delete (`active=false`) by default vs hard-delete with confirm? My default: soft. Hard delete only via a flag in the API + a "permanently delete" button in UI.
3. **Initial seed of topics.** Want me to draft the topic YAMLs based on the lit-stream outline (photometric classification / multimodal FMs in astronomy / missing-modality learning / generative cross-modal imputation / sim-to-real) plus the two foundations? That would give Phase 0 a complete out-of-the-box content set.
4. **University-library API.** Worth confirming scope with the library liaison so we know whether it's in scope by the time we hit Phase 2's paper-source plugin work?
5. **Cloudflare Access for auth.** OK to plan around it (vs building in-app auth later)? Less code to write, leverages your existing CF account, but ties your auth story to Cloudflare.
