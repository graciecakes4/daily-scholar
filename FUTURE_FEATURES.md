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

- **Phase 1 · Login & Identity**: in-progress — signup/login/session auth is live; self-serve password reset (li3b) has shipped via real SMTP email, no gaps left here.
- **Phase 2 · Admin Controls**: in-progress — role gate + a 7-tab admin console (approvals/invites/users/audit/topics/cache/stats) shipped. Cache-bust is per-user only for now — see Phase 6 for the planned multi-select + global-clear follow-up.
- **Phase 3 · Push Notifications Surface**: in-progress — settings page, per-type scheduling, and dead-subscription cleanup all shipped and more general than scoped; the actual "enable push" subscribe button isn't wired into any page yet.
- **Phase 4 · Frontend Test Infrastructure**: proposed — confirmed nothing has been built here yet.
- **Phase 5 · Frontend UI Enhancements**: in-progress — fd3's foundation (theme + font-size plumbing, three themes, `/settings/display`) shipped; fd3's longer theme list and fd0/fd1/fd2/fd4 are all still not started. See fd3 entry for the split.

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

> **Phase brief.** The server-side Web Push primitive already shipped (VAPID + pywebpush + `push_subscriptions` table + service-worker registration) but nothing called it — no opt-in UI, no per-event granularity, no scheduled trigger. **Status: in-progress** — everything except the actual subscribe-button UI is wired end-to-end, and the notification-type system that shipped is considerably more general than what was originally scoped.

- [x] **pn1** `/settings/push` subscription UI
  *Scaffolded, not wired up. `frontend/hooks/useWebPush.ts` fully implements permission request → `pushManager.subscribe()` → `POST /push/subscribe`, graceful-503 handling for an unconfigured deployment, and even a `sendTest()` helper — but no page or component in the app actually calls this hook yet. It's currently dead code.*
- [x] **pn2** Per-event notification toggles
  *Shipped, as a more general system than scoped. Instead of three fixed booleans (`push_daily_paper` / `push_topic_review` / `push_quiz_ready`), `backend/services/notifications.py` ships a registry (`study_reminder`, `paper_drop`, `weekly_status`, `quiz_nudge`), each with its own enable flag **and** a user-editable cron schedule, rendered at `/settings/notifications`.*
- [x] **pn3** Scheduled push wire-up
  *Shipped, further along than scoped. `backend/services/scheduler.py` runs a static nightly daily-content job plus one dynamic APScheduler job per (user, enabled notification type), reloaded whenever `/notifications/settings` is mutated — not just a single flag check inside one nightly job.*
- [x] **pn4** Subscription lifecycle hygiene
  *Shipped in `backend/services/push_sender.py` — a `WebPushException` with status 404 or 410 deletes the `push_subscriptions` row inline.*

**Open questions**

- [x] Does this need Login (Phase 1) first? *Resolved: no. Push subscriptions still key off the plain `user_id` string and are unaffected by the users-table work.*
- [x] iOS 16.4+ install requirement messaging — still open, and moot until pn1 actually ships a subscribe UI to put the messaging in.
- [ ] VAPID key rotation story — not documented; `docs/DEPLOY.md` only notes using different VAPID keys per environment, not the "rotation invalidates every subscription" caveat.

**Out of scope (deferred to followups)**

- Per-topic push toggles — still out.
- Quiet hours / Do Not Disturb window — still out.
- Push notification grouping on iOS — still out.
- "Try a test push" button — **partially shipped anyway**: `POST /push/test` exists in `backend/api/push.py` and `sendTest()` is implemented in `useWebPush.ts`, ahead of the UI that would surface it.

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
  *Not started*
  - [ ] notebooklm
  - [ ] llm chat
  - [ ] Notion integration
  - [ ] Obsidian integration
  - [ ] Roam integration
  - [ ] Logseq integration
  - [ ] Zotero integration
  - [ ] Mendeley integration
- [ ] **fd1** additional notification settings
  *Not started*
  - [ ] Per-topic push toggles
  - [ ] Quiet hours / Do Not Disturb window
  - [ ] Push notification grouping on iOS
- [ ] **fd2** Add new fonts
  *Not started*
  - Add Merriweather font
  - Add Source Sans 3 font
  - Add settings to `/settings/display`
- [ ] **fd3** Add user selected themes
  *Foundation shipped; the longer theme list is still open — kept unchecked
  at the fd3 level since it isn't fully landed. One theme selector (per the
  scoping call above), not a separate light/dark toggle + style layer.*
  - [x] Theme + font-size plumbing — `UserSettings.display_settings` JSON column (alembic `0014`), `backend/services/display.py` registry + get/update helpers, `backend/api/display.py` (`GET/PUT /display/settings`, `GET /display/themes`, `GET /display/font-sizes`). Colors in `tailwind.config.js` now resolve through CSS variables (`rgb(var(--x) / <alpha-value>)`) instead of literal hex, so a theme swap is a `data-theme` attribute change on `<html>` — no rebuild. Learned the hard way that a bare `var(--x)` hex string builds without error but silently drops any Tailwind utility using a `/NN` opacity modifier (`bg-rust/5`, `border-moss/25`, etc. all over the app) — fixed by storing each CSS variable as space-separated R G B components instead.
  - [x] Dark/light mode — `[data-theme="dark"]` in `globals.css`, same editorial fonts and layout, recolored for low light.
  - [x] observatory (see `mockups/stats_bar_option3_observatory.html`) —`[data-theme="observatory"]`, near-black instrument-panel palette +Bodoni Moda display face (added to the existing Google Fonts `@import`).
  - [x] Font size options (small / medium / large / extra large) —`[data-font-size="..."]` sets the `<html>` root font-size (15/17/19/21px); every rem-based Tailwind utility scales from it, no per-component changes.
  - [x] Add settings to `/settings/display` — theme cards + font-size picker, live-previews on click, `Save` persists. Nav entry added to `Sidebar.tsx` and `MobileTabBar.tsx` under a new "Appearance" group.
  - [x] Make sure themes work on all pages — the first pass of this claim was wrong: ~29 files (login/signup/onboarding, dashboard, papers, quiz, topics, admin console, most of settings/scope, a few shared components) predated the editorial reskin and still hardcoded the legacy Tailwind palette (`bg-white`, `text-slate-*`, plus `rose`/`emerald`/`amber`/`blue`/`purple`/`violet`/`red`/`green`/`yellow`/`orange` for badges and buttons — ~1,000 occurrences total). A user caught it live: the `/settings/scope/browse` cards stayed white while the rest of the app went dark under observatory. Converted all 29 files to the theme tokens via a scripted, reviewed mapping (neutrals → `paper`/`ink`/`muted`/`rule`; rose+red → `rust`; emerald+green → `moss`; amber/yellow/orange + blue/indigo/purple/violet → `gold`, since the editorial palette only has three accents). Caught and fixed two real regressions the mechanical pass introduced along the way: (1) several base/hover shade pairs (e.g. `bg-white` + `hover:bg-slate-50`, `text-slate-400` + `hover:text-slate-600`, `bg-emerald-600` + `hover:bg-emerald-700`) collapsed onto the same token, silently killing the hover effect — fixed by giving each pair distinct targets, and by using `hover:brightness-90` (a filter, not a fixed color) for the "-600 base / -700 hover" solid-button idiom instead of inventing new hex constants. Verified via `tsc --noEmit`, a direct Tailwind CLI compile (confirming every generated class — including the opacity- and hover-modified ones — actually resolves), and a scripted scan for any remaining same-token base/hover pairs (zero found). One accepted, disclosed limitation: a couple of dashboard tabs that previously used three distinct accent colors (blue/emerald/purple) now share `gold` for two of them, since the editorial palette has no fourth accent — cosmetic, not a contrast/functionality issue. Not independently visually verified in a browser (sandbox can't run a full `next build` — Google Fonts fetch is network-blocked here); worth a `npm run dev` skim before merging, especially the admin console (the largest diff, ~280 replacements). **Follow-up (caught via a real screenshot):** the color sweep above only fixes elements that had a *wrong* color class — it doesn't add one where none existed. 57 native `<input>`/`<select>`/`<textarea>` elements across 19 files (login/signup/reset-password/onboarding, admin console, topic forms, scope generate/edit, ChipListEditor) had `border-rule` styling but no `bg-*`/`text-*` class at all, so they rendered with the browser's default white background and black text regardless of theme — visible as stark white text boxes and dropdowns under dark/observatory. Fixed by adding `bg-paper text-ink` to each (scripted insertion, verified against `tsc` + a Tailwind compile). Also added `color-scheme: light` (`:root`) / `color-scheme: dark` (`[data-theme="dark"]` and `[data-theme="observatory"]`) to `globals.css`, since a `<select>`'s open dropdown popup and a date-input's calendar picker are OS-drawn and mostly ignore page CSS — `color-scheme` is the one lever that reaches them.
  - [ ] Themes — *not started, registry ready for it (append to `THEMES` in `backend/services/display.py` + a matching `[data-theme="..."]` block)*
    - pastel
    - muted
    - high contrast
    - pride
    - colorful accents
      - red
      - blue
      - green
      - purple
      - orange
    - black and white
    - random
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
