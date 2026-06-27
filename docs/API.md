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

The active scope decides which topics drive paper discovery, topic review, and quiz generation. Each user has a library of saved scopes (system-owned starters + their own + scopes shared with them); exactly one is active at a time.

### Legacy shim — used by paper discovery / quiz code

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user/scope` | Currently-active scope projected as `{scope_mode, scope_topic_ids}` |
| `PUT` | `/user/scope` | Update the active scope's mode + topic_ids in place |

### Active scope

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/user/active-scope` | The full active `Scope` row, or `null` if no scope is active yet |
| `PUT` | `/user/active-scope` | Switch which scope is active. Body: `{"scope_id": <id> \| null}`. `null` clears (drops the user back onto the onboarding picker) |

### Scope library — first-class shareable scopes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/scopes/mine` | Library view — every scope I own plus every private scope I have a grant for. Each item carries `relation: "owned" \| "granted"` |
| `GET` | `/scopes/search?q=&limit=` | Public-scope search by name + description substring. Includes system-owned starters. `limit` defaults to 50, capped at 200 |
| `GET` | `/scopes/{id}` | View one scope. Returns 404 (not 403) when not viewable so private-scope existence isn't leaked |
| `POST` | `/scopes` | Create a new scope owned by the caller. Body: `{name, description?, visibility?, scope_mode?, scope_topic_ids?}` |
| `PUT` | `/scopes/{id}` | Patch editable fields. Owner / admin only. Same body shape as POST, all fields optional |
| `DELETE` | `/scopes/{id}` | Hard-delete (204). Owner / admin only. Clears `UserSettings.active_scope_id` pointers, breaks fork lineage (SET NULL on children), drops grants + requests |
| `PUT` | `/scopes/{id}/visibility` | Flip between public/private. Body: `{"visibility": "public" \| "private"}` |
| `POST` | `/scopes/{id}/fork` | Fork an accessible scope into the caller's library as a new private row. Body: `{name?, description?}` (defaults to "Fork of <source.name>") |

### Access requests — private-scope sharing (recipient requests, owner approves)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/scopes/{id}/access-requests` | Request view-access to a private scope. Body: `{"message": "<optional>"}`. 409 if a pending request already exists, the caller is the owner, or they already have a grant |
| `GET` | `/scopes/access-requests/incoming?status=` | Requests targeted at scopes I own. `status` defaults to `pending`; valid values: `pending` \| `approved` \| `denied` (omit for all) |
| `GET` | `/scopes/access-requests/outgoing?status=` | Requests I've submitted (default: all statuses) |
| `POST` | `/scopes/access-requests/{id}/decide` | Owner-only. Body: `{"decision": "approve" \| "deny"}`. Approving inserts a `ScopeAccessGrant`; denying just stamps the row |

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

# Silo on a single topic (legacy shim — writes to the active scope)
curl -X PUT http://localhost:8000/user/scope \
  -H "Content-Type: application/json" \
  -d '{"scope_mode": "silo", "scope_topic_ids": ["transient-photometric-classification"]}'

# Fork a public starter into my library
curl -X POST http://localhost:8000/scopes/12/fork \
  -H "Content-Type: application/json" \
  -d '{"name": "My take on Physics"}'

# Switch which scope drives the app
curl -X PUT http://localhost:8000/user/active-scope \
  -H "Content-Type: application/json" \
  -d '{"scope_id": 17}'

# Request access to a private scope
curl -X POST http://localhost:8000/scopes/42/access-requests \
  -H "Content-Type: application/json" \
  -d '{"message": "Working on a related literature review"}'
```
