# Future Features — Tracker

Tracker for substantial features under consideration for Daily Scholar. Not a backlog — small bugs and polish go in GitHub Issues. This file is for things that need scoping conversation before they're issue-ready: where the architectural shape, dependencies, or open questions matter more than the line-by-line work.

**Conventions:**

- `[ ]` = scope item not yet decided/built, `[x]` = decided or landed
- Phase-level status shown in the phase brief — don't check off scope items until the design question they depend on is actually resolved
- Italic text after an item is a contextual note; edit freely

**Status legend:**

- **proposed** — captured here; no scoping done yet.
- **scoping** — actively shaping the design; open questions being resolved.
- **scheduled** — scoped + sequenced; landing in a named release.
- **in-progress** — branch open.
- **deferred** — explicitly paused with a gating condition documented.
- **shipped** — done; entry kept for one release as historical pointer, then moved to `CHANGELOG.md` and deleted from here.

---

## Status overview

- **Phase 1 · Login & Identity**: in-progress — signup/login/session auth is live; self-serve password reset (li3b) has shipped via real SMTP email; session/device management (li6) shipped in v2.7, no gaps left here.
- **Phase 2 · Admin Controls**: in-progress — role gate + a 7-tab admin console (approvals/invites/users/audit/topics/cache/stats) shipped. Cache-bust is per-user only for now — see Phase 6 for the planned multi-select + global-clear follow-up.
- **Phase 3 · Push Notifications Surface**: in-progress — settings page, per-type scheduling, dead-subscription cleanup, and (as of v2.7) the subscribe UI itself all shipped; per-topic toggles, quiet hours, and iOS notification grouping are still out.
- **Phase 4 · Frontend Test Infrastructure**: proposed — confirmed nothing has been built here yet.
- **Phase 5 · Frontend UI Enhancements**: in-progress — fd2 and fd3 are fully shipped (fd3: 10 themes — editorial, dark, observatory, soft morning, noir, brutalist, muted, high contrast, pride, random — plus multi-hue accent pickers on soft morning, noir, and high contrast; fd2: a theme-independent reading-font picker for generated content); fd0's notebooklm export is scoped and in-progress, fd0's in-house podcast generator is scoped (build-our-own, not a fork — see below), fd0's llm chat item plus fd1/fd4 are still not started. See fd3 entry for the one small new item discovered along the way (Random's rotation cadence).

---

## Phase 1 · Login & Identity

> **Phase brief.** Native login UI replacing or augmenting the Cloudflare Access gate. CF Access works for the closed beta (~30 users, email-policy gated) but doesn't scale to a wider audience — every new tester needs a manual email add, and the CF login flow has no relation to Daily Scholar's UX. A real login unlocks self-serve onboarding and a place to surface user settings CF Access can't (display name, push prefs, etc.). **Status: in-progress** — core auth (`backend/api/auth.py`, `backend/database.py`, alembic `0003`/`0005`/`0006`/`0009`) is live; it coexists with Cloudflare Access rather than replacing it (see resolved open question below).

- [x] **li1** Email + password registration + login
  *Shipped in `backend/api/auth.py` (`/auth/signup`, `/auth/login`). Hashing uses bcrypt via `passlib` (`backend/services/auth_security.py`), not Argon2 as originally scoped — the `CryptContext` is deliberately set up so swapping to argon2id later is a deprecation-list change, not a rewrite.*
- [x] **li2** Cookie-based session management
  *Shipped: `ds_session` cookie (HttpOnly + secure, `backend/api/auth.py::_set_session_cookie`) backed by an opaque, revocable `sessions` table (`backend/database.py::Session`) rather than a signed itsdangerous token. Same "no JWT, no refresh-token dance" goal, DB-backed instead.*
- [x] **li3a** Login / register / logout pages
  *Shipped as `frontend/app/login` and `frontend/app/signup` (register). Logout is a POST action wired into `UserMenu`/`Sidebar` rather than its own route — no dedicated page needed for it.*
- [x] **li3b** `/auth/forgot-password` page
  *Shipped as originally scoped, via real SMTP email. `POST /auth/forgot-password` (`backend/api/auth.py`) looks up the account by email and, if it's active, emails a link containing a single-use `password_reset_tokens` row (30 min TTL) — sending goes through `backend/services/email.py` (stdlib `smtplib`, no new dependency), configured by the `SMTP_*` settings in `backend/config.py` / `.env.example`. The endpoint always returns the same generic "if that account exists, check your email" message regardless of match, so it can't be used to enumerate which emails have accounts. The frontend (`frontend/app/forgot-password`, `frontend/app/reset-password`) just shows that message and, separately, consumes `?token=` from whatever link the email contained. An earlier iteration of this shipped with an email+username knowledge check instead of real email (no proof of inbox ownership) — replaced once SMTP was set up, since inbox-ownership proof is the stronger and correctly-scoped identity check.*
- [x] **li4** New `User` SQL model
  *Shipped (`backend/database.py::User`) — matches the scoped shape (`email`, `user_id`, `password_hash`, `status`, `role`, timestamps) plus two extras not originally scoped: `onboarded` and `tour_state` (JSON) for the onboarding wizard.*
- [--] **li5** Migration helper: `migrate_email_user_ids_to_users_table.py`
  *Turned out unnecessary as scoped. Alembic `0005_users_and_sessions.py` notes the existing 9 user-scoped tables already stored `user_id` as a plain string (email or handle), so nothing needed backfilling or re-keying — the `users` table was added additively instead. `scripts/reassign_user_id.py` covers the separate, narrower concern of a user changing their handle post-signup.*
- [x] **li6** Session (device) management UI
  *Shipped in v2.7. New `/settings/account/sessions` page lists active `sessions` rows — device/browser parsed from `user_agent`, raw `ip`, relative last-active time — with per-session revoke and a "log out everywhere else" action. The `sessions` table (`li2`) already had `user_agent`/`ip`/`created_at`/`expires_at`/`revoked_at` and a full revoke service layer built for the password-change flow; its own docstring flagged the session-list UI as "a follow-up phase," which this closes. New: `list_sessions_for_user()` / `revoke_session_by_id()` (`backend/services/auth_sessions.py`), three endpoints on `auth_router`, and a `last_seen_at` column (migration `0015_session_last_seen`) written on a 15-minute throttle. Deliberately kept separate from the push-subscription "This device" card on `/settings/notifications` (`pn1`) — different table, different identity shape (`PushSubscription.user_id` is a string handle, `Session.user_id` is an integer FK), different lifecycle.*

**Open questions**

- [x] Coexist with Cloudflare Access, or replace it? *Resolved: coexist — the opposite of this doc's original "replace" lean. `backend/auth.py`'s resolution chain checks the session cookie first, then falls through to the CF Access header → CF JWT → local-dev override → `__local__` sentinel, so CF-Access-only deployments still work.*
- [x] Invite-only or open registration? *Resolved: invite-only, and stricter than scoped. Signup requires a valid `invite_code` (unless `OPEN_SIGNUP=1` for local dev) AND lands in `pending` status requiring a separate admin-approval step (`admin_approvals.py`) before the account can do anything.*
- [x] Password reset transport — which SMTP provider? *Resolved: generic SMTP, not a specific provider — any standard SMTP server works (Gmail app password, Mailgun, SES SMTP endpoint, a self-hosted relay, etc.) via the `SMTP_*` env vars documented in `.env.example` and `docs/DEPLOY.md`. `backend/services/email.py` uses stdlib `smtplib`, so no email SDK dependency was needed. When `SMTP_HOST` is unset (fresh local checkout, no creds yet) it logs the reset link instead of sending, so the flow stays testable with zero setup.*

**Out of scope (deferred to followups)** — unchanged, none of these are built:

- OAuth (Google / GitHub / Apple Sign-In) — its own future entry once Login lands.
- Email verification flow.
- Magic-link login.
- TOTP / WebAuthn second factor.

**Dependencies**

- `passlib` is present, but with the `bcrypt` scheme rather than the `argon2` extra originally scoped; `itsdangerous` was never added since sessions are DB-backed instead of signed tokens; li3b's email sending uses stdlib `smtplib`, so still no third-party email SDK dependency in `requirements.txt`.
- The FK-rewrite migration piece turned out to be moot — see li5.

---

## Phase 2 · Admin Controls

> **Phase brief.** In-app admin role + a small admin UI for ops tasks that today require shell access or direct DB writes (cache busts, topic re-bootstraps, user-activity debugging). `/admin/*` endpoints exist server-side but have no in-app role check — gated only by Cloudflare Access. **Status: in-progress** — the role gate and a 7-tab admin console shipped (approvals/invites/users/audit/topics/cache/stats).

- [x] **ad1** `users.role` column (`'user' | 'admin'`, default `'user'`)
  *Shipped (`backend/database.py::User.role`). Seeded via `scripts/create_admin.py` rather than a `flask admin grant` command — this stack is FastAPI, not Flask.*
- [x] **ad2** `require_admin` dependency
  *Shipped in `backend/auth.py::require_admin`, applied across `admin.py`, `admin_accounts.py`, `admin_approvals.py`, `admin_invites.py`, `admin_audit.py`.*
- [x] **ad3** `/admin/users`-equivalent page
  *Shipped as the "Users" tab in `frontend/app/settings/admin/page.tsx` — list/search, per-user stats (`GET /admin/users/{id}/stats`), and soft-disable via a status change to `suspended` (string status field rather than a boolean `is_active`, same effect).*
- [x] **ad4** `/admin/topics` page
  *Shipped as the "Topics" tab in `frontend/app/settings/admin/page.tsx`. The backend half (`POST /topics/import-yaml`, `POST /topics/export-yaml`, `GET /topics?include_orphaned=`) already existed — this was purely the missing UI: Import/Export buttons with a result summary, an orphaned-only filter, and active/orphaned/system-vs-user-owned badges per topic. Deeper per-topic editing still happens on the existing `/topics/[id]/edit` page rather than being duplicated here.*
- [x] **ad5** `/admin/cache` + `/admin/stats` pages
  *Shipped as "Cache" and "Stats" tabs. **Cache**: `DELETE /admin/cache/{user_id}` (`backend/api/admin.py`) clears every `daily_content_cache` row for one target user, looked up via the same account list the Users tab already fetches — no separate lookup endpoint needed. Scoped to a single user for this PR; see **Phase 6** for the planned multi-select + global-clear follow-up. Every bust is audit-logged (`EventType.CACHE_BUST`). **Stats**: `GET /admin/stats/overview` (user counts by status, content volume, 30-day signup trend) plus a considerably more built-out `GET /admin/stats/quiz-performance` — overall/median/average score, score distribution, per-topic and per-difficulty accuracy breakdowns (worst-performing topics surfaced first), a 30-day score trend, and two leaderboards (most active, highest accuracy — the latter gated behind a minimum-questions-answered floor so a single lucky quiz can't top the board). All derived from existing `ArchivedQuiz.questions` JSON (topic_id + difficulty + correct/incorrect are already stored per question) — no new instrumentation needed. Every aggregation is fetch-then-bucket-in-Python rather than dialect-specific SQL (`date_trunc`/`strftime` differ between SQLite and Postgres), fine at beta scale. No charting library exists in this project, so the visualizations are hand-rolled CSS bars/sparklines rather than a new frontend dependency.*
- [x] **ad6** Admin-only nav surface
  *Shipped — `Sidebar.tsx`, `UserMenu.tsx`, and `MobileTabBar.tsx` all gate the admin link on `user.role === 'admin'`.*

**Open questions**

- [ ] Should admin actions push-notify the affected user (e.g. "an admin disabled your account")? *Still open — no such notification kind exists yet.*

**Out of scope (deferred to followups)**

- Audit log of admin actions — **actually shipped anyway.** `AdminAuditEvent` (`backend/database.py`) + `admin_audit.py` + the "Audit log" tab is a full append-only log of approve/reject/role-change/status-change/invite events. This doc had deferred it "until admin headcount > 1"; it landed bundled into the same admin-console work instead.
- Multi-tenant admin (org-scoped vs. system admins) — still out.
- Impersonation / "view as user" mode — still out.

**Dependencies**

- Blocked by Phase 1 — now satisfied; Phase 1's `users` table shipped.

---

## Phase 3 · Push Notifications Surface

> **Phase brief.** The server-side Web Push primitive already shipped (VAPID + pywebpush + `push_subscriptions` table + service-worker registration) but nothing called it — no opt-in UI, no per-event granularity, no scheduled trigger. **Status: in-progress** — the subscribe UI (pn1) shipped in v2.7, closing the last gap in the core surface; per-topic toggles, quiet hours, and iOS grouping are still out.

- [x] **pn1** Push subscription UI
  *Shipped in v2.7 — as a "This device" card on `/settings/notifications` rather than a dedicated `/settings/push` page as originally scoped, since it's a natural fit alongside the per-type notification toggles already living there. `frontend/hooks/useWebPush.ts` (permission request → `pushManager.subscribe()` → `POST /push/subscribe`, graceful-503 handling, `sendTest()`) had been fully implemented since Phase 3's earlier rounds but was never called from any page — confirmed dead code via a repo-wide grep before this shipped. Also surfaces explicit messaging for unsupported browsers and for iOS Safari specifically when the app hasn't been added to the home screen yet (see the resolved open question below). A CSRF gap was found and fixed in the same PR — the hook's raw `fetch()` calls bypassed `lib/api.ts`'s automatic CSRF header injection, so every subscribe/unsubscribe/test call 403'd the first time this was actually exercised; see `CHANGELOG.md` under `[v2.7]`.*
- [x] **pn2** Per-event notification toggles
  *Shipped, as a more general system than scoped. Instead of three fixed booleans (`push_daily_paper` / `push_topic_review` / `push_quiz_ready`), `backend/services/notifications.py` ships a registry (`study_reminder`, `paper_drop`, `weekly_status`, `quiz_nudge`), each with its own enable flag **and** a user-editable cron schedule, rendered at `/settings/notifications`.*
- [x] **pn3** Scheduled push wire-up
  *Shipped, further along than scoped. `backend/services/scheduler.py` runs a static nightly daily-content job plus one dynamic APScheduler job per (user, enabled notification type), reloaded whenever `/notifications/settings` is mutated — not just a single flag check inside one nightly job.*
- [x] **pn4** Subscription lifecycle hygiene
  *Shipped in `backend/services/push_sender.py` — a `WebPushException` with status 404 or 410 deletes the `push_subscriptions` row inline.*

**Open questions**

- [x] Does this need Login (Phase 1) first? *Resolved: no. Push subscriptions still key off the plain `user_id` string and are unaffected by the users-table work.*
- [x] iOS 16.4+ install requirement messaging — *Resolved in v2.7, shipped alongside pn1: the "This device" card detects iOS Safari running outside standalone/installed mode and shows an inline hint to Add to Home Screen first, instead of just silently reporting push as unsupported.*
- [ ] VAPID key rotation story — not documented; `docs/DEPLOY.md` only notes using different VAPID keys per environment, not the "rotation invalidates every subscription" caveat.

**Out of scope (deferred to followups)**

- Per-topic push toggles — still out.
- Quiet hours / Do Not Disturb window — still out.
- Push notification grouping on iOS — still out.
- "Try a test push" button — **shipped in v2.7** as part of pn1: `POST /push/test` (`backend/api/push.py`) and `sendTest()` (`useWebPush.ts`) existed since an earlier release; the "This device" card now surfaces it as a "Send test push" button once subscribed.

**Dependencies**

- No new env vars beyond the existing `VAPID_*` triplet; no new external deps (`pywebpush` already pinned).
- Migration used JSON on `user_settings.notification_settings`, matching the "lean JSONB over fixed booleans" call.

---

## Phase 4 · Frontend Test Infrastructure

> **Phase brief.** Zero frontend test infra today — no Jest/Vitest, no Testing Library, no config, no prior test files under `frontend/`. Bootstraps the first framework and lands coverage scoped-but-deferred while building the generate-scope wizard (`/settings/scope/generate`, `ChipListEditor.tsx`). **Status: proposed** — confirmed still nothing built here.

- [ ] **ft1** Test tooling setup
  *Not started — no `vitest`, `@testing-library/*`, or `jsdom` in `frontend/package.json`; no `vitest.config.ts`.*
- [ ] **ft2** `ChipListEditor` interaction tests
  *Not started — the component itself exists (`frontend/components/ChipListEditor.tsx`), but has zero tests.*
- [ ] **ft3** `dedupe()` helper tests
  *Not started — the helper exists (`frontend/app/settings/scope/generate/page.tsx`), but has zero tests.*
- [ ] **ft4** Generate-scope wizard `handleCreate` tests
  *Not started.*

**Open questions**

- [ ] Vitest vs. Jest? *Lean: Vitest — faster to wire into the existing Next.js/TS setup with fewer transform-config headaches, and the more common default for newer Next.js projects.*
- [ ] Should this be the moment frontend tests start running in CI? *There's no frontend CI job at all today — adding tests nothing runs automatically defeats the point, worth deciding alongside.*

**Out of scope (deferred to followups)**

- Full page-level snapshot tests — brittle, low signal.
- End-to-end / Playwright coverage — bigger lift than this warrants; no e2e infra exists either.
- Testing the static `ARXIV_CATEGORIES` taxonomy list — nothing meaningfully breaks if it goes stale.
- Retrofitting tests onto other existing frontend pages/components — scoped to what the generate-scope feature introduced, not a general "add frontend tests" initiative.

**Dependencies**

- None blocking — can land independently at any time.
- Loosely related: the backend's `pytest` suite (`backend/tests/`, comprehensive) also isn't invoked by CI today — `.github/workflows/` only runs Alembic migration checks. Worth bundling a fix for that gap if a frontend CI job gets added, since it's the same category of problem.

---

## Phase 5 · Frontend UI Enhancements

> **Phase brief.** Update front end ui and ux. **Status: in-progress** — fd3's foundation slice shipped (see below); fd0/fd1/fd2/fd4 and the rest of fd3 are still not started.

- [ ] **fd0** Integrations
  - [ ] notebooklm — **in-progress**, scoped as of 2026-07-05.
    *Google has no public consumer API for NotebookLM — only a paid NotebookLM Enterprise API (GCP project + Gemini Enterprise/Education Premium license), which is too heavy for a ~30-user beta. Scoped as a manual handoff instead: NotebookLM itself already provides both target use cases (audio overviews, chat/Q&A over sources) once it has sources, so Daily Scholar's job is just getting the right files there with minimal friction, not reimplementing either capability.*
    - [ ] V1: per-topic-review "Export to NotebookLM" action — zips the review's linked archived-paper PDFs plus a rendered markdown of the review content (key points, connections, practice suggestions, notes), triggers a download, and opens notebooklm.google.com in a new tab with on-screen instructions to drag the files into a new notebook.
    - [ ] Landing surface: `frontend/app/topics/archive/page.tsx` (existing per-topic-review card). Backend: new topic→PDF resolver off `ArchivedTopicReview.linked_paper_ids` (a clean indexed list of `ArchivedPaper.id`, unlike the unindexed JSON-filter pattern `notifications.py` uses for `ArchivedPaper.linked_topic_ids`), a new zip-bundling service, and a new streaming export endpoint.
    - *Out of scope for V1 — deferred, not decided against:* pushing the bundle straight to the user's Google Drive (skips the manual-upload step, since NotebookLM can add sources from Drive) — no Google OAuth infrastructure exists in this repo today, so this is a real follow-up once Login/Phase 1 patterns could be extended, not a beta-blocking need. **Gating condition:** WHEN manual zip-then-drag-in proves too clunky for beta testers, or WHEN Google ships a public consumer API.
    - *Superseded in part by the in-house podcast generator below:* once that ships, it becomes the primary path for the audio-overview use case; the NotebookLM export stays as the path for the chat/Q&A-over-sources use case, which the podcast generator does not attempt to replace.
  - [ ] in-house podcast generator (audio overviews) — **scoping**, as of 2026-07-06.
    *Explored forking three open-source options first: [podcastfy](https://github.com/souzatharsis/podcastfy) (Apache-2.0, 6.3k★, supports free/keyless Edge-TTS), [podcast-creator](https://github.com/lfnovo/podcast-creator) (MIT, actively maintained, powers the real `open-notebook` NotebookLM clone, but no free TTS provider), and [podcast-llm](https://github.com/evandempsey/podcast-llm) (CC BY-NC, stale, ruled out). Prototyped podcastfy directly: confirmed it installs and imports fine despite a stated Python 3.11+ floor, but also surfaced a live bug in the 0.4.3 release — `content_generator.py` unconditionally pulls its conversation prompt from LangChain Hub at generation time, and a newer LangSmith client now blocks that pull by default, breaking a fresh `pip install podcastfy` independent of any environment issue. Wrote and verified a patch removing that dependency entirely. Decision: build our own instead of forking or adopting either library — the real value in both (tuned dialogue prompts, audio-stitching, multi-provider TTS abstraction) is outweighed by inherited dependency bloat (podcastfy alone pulled 380+ packages for a "free-tier" run: sphinx, pandas, three LLM SDKs, none of which we need) and ongoing upstream-patch maintenance. A from-scratch version reuses Daily Scholar's own `backend/services/llm/` provider abstraction and the storage service already built for the NotebookLM export, needs only the standalone `edge-tts` PyPI package (MIT, tiny, no framework baggage) plus `pydub` for stitching, and is explicitly also a deliberate learning project (prompt design for spoken dialogue, TTS API mechanics, audio stitching) rather than pure feature delivery.*
    - [ ] V1 — single narrator: one LLM call turns a topic review into a spoken-style script (reusing `render_review_markdown()`'s assembled content as input), one Edge-TTS voice reads it straight through, output stored via the existing storage abstraction (same `papers/<key>` pattern, new `podcasts/` prefix) and served back for in-app playback.
    - [ ] V2 — two-host dialogue: LLM prompt produces back-and-forth turns with speaker tags; turns are split, each synthesized with a different Edge-TTS voice, and concatenated with `pydub`. Most of the effort here is prompt iteration against real topic content (natural pacing, avoiding alternating-monologue stiffness), not code volume.
    - [ ] V3 — polish: swap-in path to a paid TTS provider (ElevenLabs/OpenAI) behind the same interface for users who want it, configurable speaker personalities/voices, progress feedback in the UI for a generation that takes real wall-clock time, retry/backoff around TTS rate limits.
    - *Out of scope for now:* background music/intro-outro production values; anything resembling NotebookLM's chat/Q&A over sources (still the NotebookLM-export path above).
    **Open questions**
    - [ ] Where does generation run — inline in the request (blocks on LLM + TTS latency), or as a background job (APScheduler already exists in this codebase for the daily-content job) with a "ready" notification via the existing push-notification registry (Phase 3)?
    - [ ] Edge-TTS has no SLA or key — it's an unofficial wrapper around Microsoft Edge's read-aloud voices, and could break or get blocked with zero notice. Worth a documented fallback (V3's paid-provider swap-in) rather than a hard beta dependency on it.
    **Dependencies**
    - Builds directly on `render_review_markdown()` / `get_papers_and_pdfs_for_topic_review()` (`backend/services/notebooklm_export.py`, `backend/database.py`) and the storage abstraction (`backend/services/storage/`) — all already shipped.
    - New deps: `edge-tts`, `pydub` (both MIT-equivalent-permissive, lightweight). No new paid API keys required for V1/V2.
  - [ ] llm chat
    *Not started, not yet scoped — separate conversation from notebooklm.*
- [ ] **fd1** additional notification settings
  *Not started*
  - [ ] Per-topic push toggles
  - [ ] Quiet hours / Do Not Disturb window
  - [ ] Push notification grouping on iOS
- [x] **fd2** Add new fonts
  *Shipped as a theme-independent reading-font picker — scoped to long-form generated content only (`.prose-scholar`), so it can't clash with each theme's own bespoke typography from fd3.*
  - [x] Add Merriweather font — `[data-reading-font="merriweather"] .prose-scholar` in `globals.css`.
  - [x] Add Source Sans 3 font — `[data-reading-font="source_sans"] .prose-scholar`; "Match theme" (default) has no override rule at all.
  - [x] Add settings to `/settings/display` — new Reading font pill picker, `READING_FONTS` registry in `backend/services/display.py`, `GET /display/reading-fonts`.
  - [x] *Incidental fix:* `.prose-scholar` was still on hardcoded `slate-*`/`blue-*` Tailwind classes — missed by the earlier app-wide theme sweep since it lives in `globals.css`, not a page file. Converted to theme tokens while this block was already being touched.
- [x] **fd3** Add user selected themes
  *Fully shipped — every item from the original theme list has landed. One theme selector (per the scoping call above), not a separate light/dark toggle + style layer.*
  - [x] Theme + font-size plumbing — DB storage, backend services/API, RGB CSS variables for instant theme switching.
  - [x] Dark/light mode — `[data-theme="dark"]` in `globals.css`, editorial fonts/layout recolored for low light.
  - [x] Observatory — `[data-theme="observatory"]`, near-black instrument panel + Bodoni Moda display face.
  - [x] Font size options (small/medium/large/xlarge) — `[data-font-size="..."]` scales the `<html>` root font-size.
  - [x] Add settings to `/settings/display` — theme cards + font-size picker, live preview, Save; nav entry in Sidebar/MobileTabBar.
  - [x] Make sure themes work on all pages — swept 29 files to theme tokens, styled 57 native inputs, fixed hover regressions.
  - [x] Soft Morning — blush pastel, rounded shapes (Fraunces + Nunito); one of two themes picked for a multi-hue accent picker.
  - [x] Noir — cold true grayscale, one electric-blue accent (Bebas Neue + Work Sans); the other multi-hue-accent theme.
  - [x] Brutalist — standalone theme, single accent only; stark black/white, hard edges, offset shadows (Archivo Black + Space Mono).
  - [x] Colorful accents (Soft Morning) — 5 pastel accents (orange/rose/sage/sky/lavender) via `THEME_ACCENTS` + `[data-accent="..."]` CSS blocks.
  - [x] Colorful accents (Noir) — 5 saturated accents (cobalt/crimson/emerald/violet/amber); same recipe, zero extra frontend code needed.
  - [x] Muted — desaturated stone/greige, single clay accent (Cormorant Garamond display face, body stays Inter).
  - [x] High Contrast — pure black/white verified against WCAG (AAA on body/secondary text, AA+ on danger red), Atkinson Hyperlegible throughout, its own 4-accent picker (cyan/orange/magenta/violet).
  - [x] Pride — clean neutral base (Fredoka + Figtree), progressive flag palette carried as a thin gradient ribbon pinned to the viewport top, not a full-flood recolor.
  - [x] Random — meta-theme, no palette of its own; `resolve_random()` hashes user + ISO week (Monday-anchored, UTC) into a pick from every other theme (+ accent, if it has one). No cron needed — the week number is the clock.
    - [ ] *New, discovered while building Random:* user-configurable rotation cadence (daily/weekly/monthly, or a custom cron-style schedule) instead of the fixed weekly reset — not started.
- [ ] **fd4** improve stats
  - add more stats
  - add interactive tiles
  - add interactive charts
  - add more granular levels

---

## Phase 6 · Admin Cache Tooling Follow-ups

> **Phase brief.** Follow-up to the Phase 2 / ad5 cache-bust tool, which shipped scoped to a single targeted user per action. This phase captures the two ways it was intentionally left narrower than it could be. **Status: proposed** — captured here, not scoped or scheduled yet.

- [ ] **ct1** Multi-user select for cache bust
  *Not started. Today the Cache tab (`frontend/app/settings/admin/page.tsx::CacheTab`) busts exactly one user's `daily_content_cache` rows per click. Extending to a multi-select (checkboxes + "Bust selected") would mean either N sequential `DELETE /admin/cache/{user_id}` calls from the frontend, or a new batch endpoint taking a list of user_ids — the latter is probably worth it once this lands, so the action is one audit-log entry instead of N.*
  *Gating condition: WHEN an admin actually needs to clear cache for more than one or two users in the same incident (e.g. after a topic-weight change affects a whole cohort's daily content).*
- [ ] **ct2** Global "clear for everyone" option
  *Not started. A single confirm-gated action that truncates `daily_content_cache` for every user_id at once — useful after a content-generation bug fix or a bulk topic overhaul, but coarse enough (and irreversible enough in effect, even though it's just cache) that it should get its own explicit confirm step separate from the per-user flow, not a checkbox that happens to select everyone.*
  *Gating condition: WHEN a beta tester reports stale content that per-user targeting doesn't fully resolve, or WHEN a content-generation change ships that's known to invalidate everyone's cache at once.*

**Dependencies**

- Builds directly on Phase 2 / ad5 (`backend/api/admin.py::bust_user_cache`, `frontend/app/settings/admin/page.tsx::CacheTab`) — not blocked by anything else.

---

## Process notes

When promoting an entry to **scheduled**, copy it to the relevant `docs/releases/vX.md` "Coming next" section and update the status here. When promoting to **shipped**, move the substantive detail to the `CHANGELOG.md` entry for that release and leave only a one-line pointer here for one release cycle, then delete.

When deferring an entry, add a **Gating condition:** line naming the specific signal that would unblock it (e.g. "WHEN admin headcount > 1" or "WHEN a beta tester asks for it"). Don't defer without a gate — it's how the tracker stays meaningful instead of becoming a graveyard.
