# Architecture

How the pieces of Daily Scholar fit together. Pair this with [LEARNING_GUIDE.md](LEARNING_GUIDE.md) for a component-by-component code walkthrough.

## System overview

```
                ┌────────────────────────────────────────────────┐
                │  Browser / installed PWA (Next.js standalone)  │
                │   • dashboard / paper reader / quiz session    │
                │   • topic catalog + in-app editor              │
                │   • settings (scope, push, notifications)      │
                │   • service worker (offline + Web Push)        │
                └─────────────────────┬──────────────────────────┘
                                      │  HTTPS
                                      │  (Cloudflare Access edge auth on hosted)
                                      ▼
                ┌────────────────────────────────────────────────┐
                │  Backend (FastAPI + uvicorn)                    │
                │   /daily  /papers  /topics  /quiz               │
                │   /push  /admin  /scope  /health  /health/deep  │
                └─────────────────────┬──────────────────────────┘
                                      │
       ┌──────────────────┬───────────┴────────────┬──────────────────┐
       ▼                  ▼                        ▼                  ▼
┌────────────────┐ ┌──────────────────┐ ┌────────────────────┐ ┌──────────────┐
│ Paper          │ │ Content Gen      │ │ Scheduler          │ │ Push fanout  │
│ Discovery      │ │ (LLM router:     │ │ (APScheduler)      │ │ (VAPID +     │
│  • arXiv       │ │  anthropic /     │ │  • nightly daily-  │ │  pywebpush)  │
│  • Semantic    │ │  gemini /        │ │    content build   │ │              │
│    Scholar     │ │  antigravity,    │ │  • per-user push   │ │              │
│  • CORE        │ │  routed per task)│ │                    │ │              │
└────────────────┘ └──────────────────┘ └────────────────────┘ └──────────────┘
                                      │
                ┌─────────────────────┴───────────────────────┐
                ▼                                             ▼
       ┌──────────────────────┐                  ┌───────────────────────┐
       │ Database              │                 │ Storage abstraction   │
       │  • SQLite (local)     │                 │  • Local filesystem   │
       │  • Postgres (hosted)  │                 │  • Backblaze B2 (S3)  │
       │  via SQLAlchemy +     │                 │  presigned URLs go    │
       │  alembic migrations   │                 │  direct to browser    │
       └──────────────────────┘                  └───────────────────────┘
```

Two switches govern environment behavior, both via env:

- `DATABASE_URL` — `sqlite:///./data/daily_scholar.db` (local default) or a Postgres URL (Railway / docker-compose).
- `STORAGE_BACKEND` — `local` (default; PDFs land under `./data`) or `b2` (Backblaze, presigned URLs).

Cloudflare Access is the only auth path on hosted deployments — there's no in-app login UI. Local mode runs as a single `__local__` user with no auth.

## Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3.10+ (3.13 recommended) | core language |
| | FastAPI + uvicorn | web framework + ASGI server |
| | SQLAlchemy + alembic | ORM + database migrations |
| | Pydantic | request/response validation |
| | APScheduler | nightly daily-content + push-notification jobs |
| | httpx | HTTP client (arXiv, Semantic Scholar, CORE) |
| | pywebpush + VAPID | Web Push fanout |
| | boto3 | S3-compatible client (Backblaze B2 backend) |
| **Database** | SQLite | default — local single-machine path |
| | Postgres 17 | hosted / docker-compose path |
| **Storage** | Local filesystem | default — PDFs under `./data` |
| | Backblaze B2 (S3 API) | hosted — presigned URLs straight to browser |
| **Frontend** | Next.js 16+ (standalone) | React framework |
| | TypeScript | type safety |
| | Tailwind CSS | styling |
| | `@serwist/next` | PWA service worker (Workbox-based) |
| **LLM providers** | Anthropic Claude | default for every task |
| | Google Gemini | optional, per-task override |
| | Google Antigravity | optional, agent-harness flavor |
| **Paper sources** | arXiv | physics, math, CS, stats (free) |
| | Semantic Scholar | broad coverage + metadata |
| | CORE | open-access aggregator |
| **Hosting (optional)** | Railway | backend + frontend + Postgres |
| | Cloudflare | DNS + TLS + Access (auth) |
| | Backblaze B2 | PDF / upload storage (zero-egress with CF) |

## Directory structure

```
daily-scholar/
├── README.md                 # pitch + quick start
├── LICENSE                   # MIT
├── SECURITY.md               # how to report vulnerabilities
├── CLAUDE.md                 # code-style + project notes for AI-assisted dev
├── .env.example              # template for required environment variables
├── .gitignore
├── .dockerignore
├── requirements.txt          # Python dependencies
├── pytest.ini                # pytest config
├── Makefile                  # `make setup` / `make start` / `make test` etc.
├── setup.sh                  # idempotent local bootstrap (called by `make setup`)
├── start.sh                  # boots backend + frontend with /health polling
├── Dockerfile                # backend image (Railway + docker-compose)
├── docker-compose.yml        # full stack: postgres + backend + frontend
├── railway.toml              # Railway deploy config (backend)
│
├── backend/
│   ├── __init__.py
│   ├── main.py               # FastAPI app + lifespan (migrations, topic bootstrap, scheduler)
│   ├── config.py             # Settings + env loaders
│   ├── database.py           # SQLAlchemy models, alembic glue, helper queries
│   ├── models.py             # Pydantic request/response schemas
│   ├── auth.py               # Cloudflare Access identity (email header + optional JWT verify)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── topics.py         # Topic CRUD, scope, import/export YAML
│   │   ├── push.py           # Web Push subscribe / unsubscribe / test
│   │   └── admin.py          # Scheduler inspection + manual job runs
│   └── services/
│       ├── __init__.py
│       ├── paper_discovery.py    # arXiv + Semantic Scholar + CORE, topic-scoped
│       ├── content_generator.py  # LLM-driven reviews + quizzes
│       ├── daily_content.py      # daily paper/review/quiz orchestration + caching
│       ├── topic_loader.py       # YAML ↔ topics-table sync (bootstrap/import/export)
│       ├── scheduler.py          # APScheduler nightly daily-content job
│       ├── push_sender.py        # Web Push fanout (VAPID + pywebpush)
│       ├── llm/                  # Multi-provider LLM router (anthropic/gemini/antigravity)
│       │   ├── interface.py
│       │   ├── factory.py        # per-task routing table + provider selection
│       │   ├── anthropic_client.py
│       │   ├── gemini_client.py
│       │   └── antigravity_client.py
│       └── storage/              # Storage abstraction (LocalStorage / B2Storage)
│           ├── interface.py
│           ├── factory.py
│           ├── local.py
│           └── b2.py
│
├── alembic/                  # database migrations (managed via SQLAlchemy)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_baseline.py
│       ├── 0002_topics_user_settings_push.py
│       └── 0003_auth_ready_user_id.py
├── alembic.ini
│
├── frontend/
│   ├── package.json          # Next.js 16, React, Tailwind, @serwist/next
│   ├── next.config.js        # Next config + Serwist PWA wrapper
│   ├── Dockerfile            # multi-stage build (deps → builder → runner)
│   ├── railway.toml          # Railway deploy config (frontend)
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── app/
│   │   ├── layout.tsx        # root layout + PWA shell
│   │   ├── page.tsx          # dashboard
│   │   ├── sw.ts             # service worker source (Serwist)
│   │   ├── globals.css
│   │   ├── papers/           # discover + archive
│   │   ├── quiz/             # quiz session pages
│   │   ├── topics/           # catalog, new, edit, archive
│   │   └── settings/         # scope, notifications
│   ├── components/           # shared React components (TopicForm, install prompts, etc.)
│   ├── lib/
│   │   └── api.ts            # typed API client
│   └── public/
│       ├── manifest.json     # PWA manifest
│       └── icons/            # PWA icons (replace with your own brand)
│
├── config/
│   └── topics/               # one YAML per topic; loaded at startup
│       ├── examples/         # tracked demo topics shipped with the repo
│       │   ├── astronomy-foundations.yaml
│       │   ├── ml-foundations.yaml
│       │   └── generic-ml.yaml
│       └── private/          # gitignored; YOUR topics live here on your fork
│
├── scripts/
│   ├── setup_db.py           # standalone DB init (rarely needed; `make setup` covers this)
│   ├── generate_vapid_keys.py    # one-time VAPID keypair for Web Push
│   ├── check_dialect_compat.py   # CI gate: exercises SQLite + Postgres parity
│   └── reassign_user_id.py       # move user-scoped rows from one user_id to another
│
├── docs/
│   ├── ARCHITECTURE.md       # this file
│   ├── API.md                # endpoint reference
│   ├── PWA.md                # PWA install + Web Push setup
│   ├── DEPLOY.md             # Railway + Cloudflare + Backblaze B2 deploy
│   ├── DEPLOY_CLOUDFLARE.md  # Cloudflare DNS + Access runbook (deep dive)
│   ├── LEARNING_GUIDE.md     # component-by-component explainer (developer onboarding)
│   └── topics.md             # Topic model reference (schema, examples, import/export)
│
├── .github/
│   └── workflows/
│       ├── test-migrations.yml   # SQLite + Postgres migration parity on PR
│       ├── deploy.yml            # Railway deploy gated on dialect-compat
│       └── claude-review.yml     # AI code review on PR
│
├── data/                     # auto-generated; SQLite DB + LocalStorage PDFs
│   └── daily_scholar.db
│
└── uploads/                  # auto-generated; uploaded course materials (gitignored)
```

A few directories are intentionally gitignored: `config/topics/private/` (your personal topics), `uploads/` (your course materials), `data/` (SQLite + PDFs), `.env` (secrets), and any internal planning docs. See [.gitignore](../.gitignore) for the full list.
