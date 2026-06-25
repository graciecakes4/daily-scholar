# Daily Scholar 📚

A self-hosted, personalized daily learning system. Fork the repo, point it at the topics you care about, and every day it delivers:

- **Fresh research papers** matched to your topics (arXiv, Semantic Scholar, CORE)
- **Topic reviews** synthesized by an LLM from your reading list
- **Interactive quizzes** with spaced repetition
- **Supplementary resources** to deepen what you're studying

Daily Scholar is designed to be your tool: you run it, you tune the topics, the data stays where you put it.

---

## Get started

> **Fork first.** Daily Scholar is shipped as source. The intended workflow is to **[fork this repo on GitHub](https://github.com/graciecakes4/daily-scholar/fork)**, clone your fork, and customize from there. Your topics, notes, and configuration belong to *your* instance — the upstream repo only ships generic example topics and the codebase.

Two ways to run your fork:

| Setup | What you get | Pick when |
|---|---|---|
| **Local** (`make setup` + `make start`) | SQLite + local filesystem; everything stays on your laptop | You want a single-machine daily driver, are evaluating the app, or are developing on it |
| **Hosted PWA** (Railway + Cloudflare + B2) | Install on your phone, push notifications, data syncs across devices | You want it available wherever you are, with mobile-friendly notifications |

The same codebase powers both. The hosted setup layers Postgres, Backblaze B2, and Cloudflare Access on top, but every cloud-only feature has a local-mode fallback or graceful skip — you can start local and graduate to hosted later without rewriting anything.

---

## Run Locally

The local-mode path is SQLite + local filesystem + local frontend. No Railway, Cloudflare, or Backblaze required.

### Prerequisites

- **Python 3.10+** (`python3 --version`) — 3.13 recommended; 3.10 is the floor because the codebase uses PEP 604 union syntax (`int | None`).
- **Node.js 18+** (`node --version`) — only required if you want the frontend; `--backend-only` mode skips it.
- **An Anthropic API key** at https://console.anthropic.com/ (free tier works for development).

### Quick start

```bash
# 1. Fork this repo on GitHub (top-right "Fork" button), then clone your fork:
git clone https://github.com/<your-username>/daily-scholar.git
cd daily-scholar

# 2. Idempotent setup: venv, deps, .env, migrations, frontend install
make setup

# 3. Paste your ANTHROPIC_API_KEY into .env (any editor):
$EDITOR .env

# 4. Boot backend + frontend, wait for /health, open the app
make start
```

That's it. The dashboard is at http://localhost:3000. Re-running `make setup` is safe — every step is idempotent.

Once `start.sh` polls `/health` to 200 (default 300s timeout; cold-start alembic migrations legitimately need that), you'll see:

```
✅ Daily Scholar is running:
   - App:        http://127.0.0.1:3000
   - API:        http://127.0.0.1:8000
   - API docs:   http://127.0.0.1:8000/docs
   - Health:     http://127.0.0.1:8000/health
```

`Ctrl-C` stops both processes cleanly.

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

If `make` isn't your thing, `./setup.sh` and `./start.sh` do the same work directly. Both accept `--help`.

### Configure your topics

The default topic set ships under `config/topics/examples/`. Add your own under `config/topics/examples/` to share, or under `config/topics/private/` to keep them out of git. To switch focus or add a new stream, see [docs/topics.md](docs/topics.md). You can edit YAMLs directly OR use the in-app editor at `http://localhost:3000/topics`.

### Daily usage

1. Open http://localhost:3000.
2. View today's content — paper summary, topic review, quiz.
3. Submit quiz answers, archive papers you want to read later, mark topics complete.
4. Explore the API at http://localhost:8000/docs.

### Optional: Web Push notifications

Local mode supports Web Push for "today's paper is ready" notifications. One-time setup:

```bash
make vapid                           # generates VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT
# paste the three printed lines into .env, then restart with make start
```

Enable notifications in the app at `/settings/scope`. Regenerating the keypair invalidates every active browser subscription — treat the keys like an API secret. Full PWA + push walkthrough in [docs/PWA.md](docs/PWA.md).

---

## Documentation

| Doc | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System diagram, directory structure, tech stack |
| [docs/API.md](docs/API.md) | Endpoint reference (Swagger at `/docs` is authoritative) |
| [docs/topics.md](docs/topics.md) | Topic model schema, YAML examples, import/export |
| [docs/PWA.md](docs/PWA.md) | Install as a PWA, offline behavior, Web Push setup |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Hosted deploy: Railway + Cloudflare + Backblaze B2 + docker-compose + multi-LLM routing |
| [docs/DEPLOY_CLOUDFLARE.md](docs/DEPLOY_CLOUDFLARE.md) | Cloudflare DNS + Access runbook (deep dive) |
| [docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md) | Component-by-component code explainer |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `setup.sh` fails on `pip install` | confirm `python3 --version` is 3.10+; older versions reject PEP 604 syntax in `requirements.txt` |
| Backend won't start, says `ANTHROPIC_API_KEY` not set | edit `.env` to add your key |
| `make start` times out on `/health` | check the uvicorn output above the timeout — usually a missing env value or a port-3000/8000 collision (run `make clean`) |
| `ImportError: attempted relative import with no known parent package` | run from project root, not from inside `backend/`: `cd ~/daily-scholar && uvicorn backend.main:app --reload` |
| "table seen_papers already exists" on `alembic upgrade head` | pre-Alembic DB — just run `make start` once and the backend's smart detection handles it |
| Frontend is slow to compile | project is on a cloud-synced volume (OneDrive / Dropbox / iCloud) — copy it to a local path (`cp -r /path/to/cloud/daily-scholar ~/daily-scholar`), then `rm -rf frontend/node_modules frontend/.next && npm install` |
| `@import rules must precede all rules` | move any `@import` statements to the very top of `frontend/app/globals.css` |
| `python` command not found | use `python3` instead |
| `npm` command not found | install Node.js (`brew install node` on macOS, or https://nodejs.org/) |
| `GET /papers/discover` returns null | check network; broaden topic scope at `/settings/scope` from `silo` to `all`; lower `min_relevance` on the relevant topic at `/topics/{id}/edit` |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT — see [LICENSE](LICENSE). You're free to fork, modify, and run your own instance. For security reports, see [SECURITY.md](SECURITY.md).
