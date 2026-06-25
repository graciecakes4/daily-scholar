# API Reference

The always-current, fully-typed API surface lives at `http://localhost:8000/docs` (Swagger UI) when the backend is running — that's authoritative. This file documents the load-bearing endpoints in a format that's easier to read at a glance; archive CRUD, history, and per-paper PDF endpoints are in Swagger.

## Core

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Lightweight health (env config + active topic count); used by Railway / Cloudflare probes |
| `GET` | `/health/deep` | Per-subsystem ping (DB, LLM keys, storage, push, arXiv, scheduler) with latency |
| `GET` | `/config/status` | Configuration snapshot — providers configured, storage backend, topic counts |
| `GET` | `/stats` | Counters for current user (papers seen / archived / completed, quizzes, streak) |

## Daily content

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/daily` | Today's paper + topic review + quiz, scoped to active topics (cached per day) |
| `GET` | `/papers/discover` | Discover papers from the active topic scope across arXiv / Semantic Scholar / CORE |
| `GET` | `/papers/daily` | Today's selected paper (without reviews / quiz) |
| `GET` | `/papers/history` | Recent papers seen |

## Topics

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/topics` | List topics (`?stream=`, `?active=`, `?include_orphaned=` filters) |
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

Full topic-model schema lives in [topics.md](topics.md).

## Quiz

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/quiz/generate/{topic_id}` | Generate a quiz for a topic |
| `POST` | `/quiz/regenerate` | Multi-topic quiz drawing from active scope |
| `POST` | `/quiz/answer` | Submit a quiz answer for evaluation |

## Scope (per-user)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/scope` | Current user's topic scope (silo / multi / all) |
| `PUT` | `/scope` | Update the topic scope |

## Web Push

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/push/vapid-public-key` | VAPID public key for browser subscription |
| `POST` | `/push/subscribe` | Register a browser push subscription |
| `POST` | `/push/unsubscribe` | Drop a subscription |
| `POST` | `/push/test` | Fire a test push to the current user's subscriptions |
| `GET` | `/push/subscriptions` | List current user's active subscriptions |

See [PWA.md](PWA.md) for the end-to-end Web Push setup.

## Admin (scheduler + multi-user inspection)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/scheduler/jobs` | List APScheduler jobs with their next-run timestamps |
| `POST` | `/admin/scheduler/run/{job_id}` | Trigger a scheduled job immediately (instead of waiting for cron) |
| `GET` | `/admin/whoami` | Identity of the current request (handy for verifying CF Access wiring) |
| `GET` | `/admin/users` | List user ids with row counts across user-scoped tables |
| `GET` | `/admin/users/{user_id}/stats` | Stats for a specific user |
| `GET` | `/admin/users/{user_id}/papers` | Paper history for a specific user |

Admin gating currently relies entirely on the Cloudflare Access policy in front of the deployment; there is no in-app role check yet. Don't open `/admin/*` to your beta cohort via CF Access until a role gate lands.

## Example calls

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
curl -X PUT http://localhost:8000/scope \
  -H "Content-Type: application/json" \
  -d '{"scope_mode": "silo", "scope_topic_ids": ["transient-photometric-classification"]}'
```
