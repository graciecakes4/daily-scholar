# Changelog

## [v2.2] — 2026-06-26

Multi-user release. Daily Scholar moves from a solo praxis tool to a real multi-tenant beta-ready app. Six feature PRs land in one release plus a code-review agent playbook commit: configurable push notifications (PR #37), the multi-user auth foundation Phases A–F bundled (PR #38 — in-app email+password signup, invite-gated admin approval, per-user topic ownership with private/public visibility, topic discovery + subscriptions, LLM-driven onboarding wizard, admin account management UI), append-only admin audit log (PR #39), self-service password + username change + admin password reset (PR #40), beta hardening (PR #41 — custom in-memory rate limiter, double-submit-cookie CSRF, password-strength UI hint), per-page guided product tours with versioned server-side state (PR #42), and `AGENTS.md` (commit f982e4a). Solo mode (`__local__`) preserved end-to-end. **Eight new migrations (0004–0011), two new Python deps (`passlib`, `bcrypt`), one new npm dep (`driver.js`), three new dev-only env knobs.**

### Added

#### Configurable scheduled push notifications (PR #37)

- New `user_settings.notification_settings JSON DEFAULT '{}'` column via migration `0004_notification_settings`. Holds per-user, per-type config: `{enabled, frequency: daily|weekly, time, day_of_week, ...type_specific}`.
- New `backend/services/notifications.py` with a `REGISTRY` of notification types (study_reminder, paper_drop, weekly_recap, quiz_review). Adding a new type is one entry — the registry drives both the API and the UI.
- New `backend/api/notifications.py`: `GET /notifications/types` (schema-driven UI metadata), `GET /notifications/settings`, `PUT /notifications/settings`, `POST /notifications/test/{type}` (sends a real push through the same dispatch path the cron uses — green test == green cron).
- APScheduler jobs are keyed `notif:<user>:<type>` so they're idempotent on settings change — toggle takes effect immediately, no restart.
- New `frontend/app/settings/notifications/page.tsx` — auto-renders one card per registry type with on/off toggle + frequency + time-of-day picker + day-of-week (weekly only) + Preview + Test buttons.

#### Multi-user auth foundation, Phases A–F (PR #38)

- **Phase A — In-app email+password auth.** Migration `0005_users_and_sessions`. New `users` table (email + user_id + password_hash + status + role + onboarded + timestamps) and `sessions` table (opaque token + user_id FK + expires_at + revoked_at + UA/IP). New `backend/services/auth_security.py` (bcrypt via passlib) + `backend/services/auth_sessions.py` (cookie issue/revoke). New `backend/api/auth.py`: `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`. `get_current_user_id` chain refactored: session cookie → CF Access header → `X-User-Id` → `__local__`. New `scripts/create_admin.py` for bootstrap. **Two-column identity split**: `users.email` = login credential, `users.user_id` = foreign-keyable handle string used by the existing 9 user-scoped tables — no refactor needed for any `user_id VARCHAR(100)` column.
- **Phase B — Invite codes + admin approval queue.** Migration `0006_invite_codes`. `/auth/signup` now requires `invite_code` body field unless `OPEN_SIGNUP=1`. New `backend/api/admin_invites.py` (generate / list / revoke) + `backend/api/admin_approvals.py` (list pending / approve / reject). **New `require_admin` dependency replaces `require_cloudflare_access` on `/admin/*`** — closes the admin-role-gate deferred since v1.1.
- **Phase C — Per-user topic ownership + visibility.** Migration `0007_topic_ownership`. `topics.owner_user_id INTEGER NULLABLE` (NULL = system/yaml topic) + `topics.visibility VARCHAR(20)` (existing rows backfill `'public'`; new rows default `'private'`). User-created topics get opaque `usr-xxxxxx` ids; yaml topics keep slugs. New `backend/services/topic_ownership.py`. Topic CRUD enforces ownership; not-visible collapses to 404 (no existence leak). `/topics/import-yaml` and `/topics/export-yaml` switched to admin-only.
- **Phase D — Topic discovery + subscriptions.** Migration `0008_topic_subscriptions`. New `topic_subscriptions` table (user_id string + topic_id FK + UNIQUE). New `backend/services/topic_subscriptions.py`. New `/topics/discover` page + search endpoint. `POST /topics/{id}/subscribe`, `DELETE /topics/{id}/subscribe`. **Scope rule changed from "system OR own OR any public" to "system OR own OR (subscribed AND still public)"** — owner flipping public→private silently drops the topic from subscribers' scope without deleting the subscription row.
- **Phase E — LLM-driven onboarding wizard.** Migration `0009_user_onboarded` (server_default `true` so existing users skip the wizard; new INSERTs default `false`). New `backend/services/onboarding.py` (LLM-drafted topic config with defensive normalization + three fallback paths). New `backend/api/onboarding.py`: `POST /onboarding/generate-topic`, `POST /onboarding/complete`. New `frontend/app/onboarding/page.tsx` (3-step wizard) + `frontend/components/OnboardingGuard.tsx` in layout.
- **Phase F — Admin account management UI.** New `backend/api/admin_accounts.py`: list (status/role filters), `PUT /admin/accounts/{id}/role` (last-admin protection), `PUT /admin/accounts/{id}/status` (refuses self-suspend, revokes all sessions on suspend). Third tab "Users" on `/settings/admin` with Promote/Demote + Suspend/Reactivate.
- Frontend identity primitives: `frontend/components/AuthShell.tsx` (extracted from `app/login/page.tsx` to satisfy Next.js page-export rule), `frontend/components/UserMenu.tsx`, `frontend/hooks/useAuth.ts` with `AUTH_CHANGED_EVENT` so layout-level components refetch `/auth/me` after login/logout. `<AuthBoundary>` redirects to `/login?next=...` on any 401. New pages: `/login`, `/signup`, `/account/pending`, `/account/suspended`, `/onboarding`, `/topics/discover`, `/settings/admin` (4 tabs).

#### Append-only admin audit log (PR #39)

- Migration `0010_admin_audit_log`. `admin_audit_log` table with denormalized actor + target identifiers so display survives if the underlying user / invite row is deleted (FK ON DELETE SET NULL).
- New `backend/services/audit_log.py`: `log_event()` is best-effort — wrapped in try/except + warning log so a DB hiccup in the logger never blocks the admin action it's auditing.
- Wired into all six admin mutations: approve, reject (target email captured), role_change (old→new in metadata), suspend, reactivate (status delta), invite create (max_uses + expiry in metadata), invite revoke (only when actually flipped — no audit noise on double-revoke).
- New `GET /admin/audit` (`backend/api/admin_audit.py`) with filters (event_type / actor / target_id / since / until) + pagination. New 4th "Audit log" tab on `/settings/admin` with color-coded event badges + click-to-expand metadata JSON.

#### Self-service password + username change + admin password reset (PR #40)

- `PUT /auth/password` — self-service password change, requires current password, revokes every OTHER session for the user (kicks hijacked devices) but preserves the current session via cookie token comparison.
- `PUT /auth/username` — self-service handle change, requires current password, cascades the new `user_id` across all 10 string-`user_id` tables in a single transaction.
- `PUT /admin/accounts/{id}/password` — admin reset, skips current-password check, revokes ALL target sessions, logs `EventType.USER_PASSWORD_RESET_ADMIN` event with only `{new_password_length: N}` in metadata (never the password itself).
- New shared `backend/services/account_management.py` with `USER_SCOPED_MODELS` as single source of truth for the cascade table list. `scripts/reassign_user_id.py` now imports it.
- New `frontend/app/settings/account/page.tsx` — change password + change handle + replay all tutorials in one place. Admin Users tab gains a "Reset password" modal with copy-to-clipboard.

#### Beta hardening — rate limit + CSRF + password strength (PR #41)

- New `backend/middleware/rate_limit.py` — custom in-memory fixed-window middleware. Default policies: `POST /auth/login` 5/min/IP, `POST /auth/signup` 3/min/IP, `POST /onboarding/generate-topic` 5/hour/user. Env flag `RATE_LIMIT_DISABLED=1` skips.
- New `backend/middleware/csrf.py` — double-submit-cookie pattern. Non-HttpOnly `ds_csrf` cookie set on every response that lacks one, `X-CSRF-Token` header required on POST/PUT/PATCH/DELETE. Env flag `CSRF_DISABLED=1` skips.
- New `frontend/components/PasswordStrength.tsx` — length-tier + character-class scorer, no `zxcvbn` (would've added ~400KB). Drop-ins on signup, change-password, and admin reset forms.
- Frontend `lib/api.ts` `fetchAPI` helper auto-attaches `X-CSRF-Token` from cookie on mutating requests, with one-shot retry on the warmup case (first request before the cookie is set).
- Mount order in `backend/main.py` is intentional: `RateLimit → CSRF → routes` (rate-limit cheaply rejects bursts BEFORE the more expensive CSRF check).

#### Per-page guided product tours with versioned server-side state (PR #42)

- Migration `0011_tour_state` (filename `0011_tour_version_seen.py` — see Decisions) adds `users.tour_state JSON NOT NULL DEFAULT '{}'` holding `{tour_id: highest_version_seen}`. Adding a new tour later requires no migration — just a new key.
- New `backend/api/auth.py` endpoints: `PUT /auth/tour-completed {tour_id, version}` uses `max(current, version)` per-key (stale-callback protection), `PUT /auth/tour-reset` clears every key. `KNOWN_TOUR_IDS = {"dashboard", "scope", "topics"}` server-side; unknown ids → 400.
- New `frontend/hooks/useDriverTour.ts` — shared driver.js plumbing (self-gates on auth loaded + user logged in + onboarded + pathname match + version unseen).
- New tour components: `frontend/components/tours/DashboardTour.tsx` (4 steps: Paper → Review → Quiz → Settings), `ScopeTour.tsx` (2 steps), `TopicsTour.tsx` (3 steps). Each is ~40 lines: STEPS + TOUR_ID + TOUR_VERSION + one `useDriverTour()` call.
- "Show all tutorials again" button on `/settings/account` calls `/auth/tour-reset`.

#### Code-review agent playbook (commit f982e4a)

- New `AGENTS.md` at the repo root — review priorities, conventions to enforce, what to skip, voice guidance for user-facing copy. Doesn't affect runtime. (Currently scoped to a FriendZone Flask app per file content — adapt for Daily Scholar's FastAPI + Next.js stack in a follow-up.)

### Changed

- **`/admin/*` now requires admin role.** Before: any CF-Access-authenticated user. After: caller must have a User row with `role='admin'`. Solo `__local__` is still treated as admin. Action required: seed your admin via `scripts/create_admin.py` BEFORE pointing the new frontend at prod.
- **Topic scope rule changed.** Before: every public topic from any user auto-appeared in everyone's scope. After: system + own + (subscribed AND still public). Existing beta users whose scope relied on auto-seeing other users' public topics need to subscribe via `/topics/discover` after this ships.
- **`/auth/signup` requires `invite_code`** in production. Set `OPEN_SIGNUP=1` only in dev / CI.
- `GET /admin/audit` joins back to `users` for the live display info but falls back to the denormalized actor_user_id / target_email if the join misses (deleted user).
- `get_current_user_id` chain ordering documented in `backend/dependencies/auth.py` — session cookie wins over CF Access header so a logged-in real user in a CF-protected tab doesn't get masked as the CF-Access subject.
- Frontend nav: `<UserMenu />` lives top-right, replacing the previous logged-in-user pill that was static.

### Fixed

- `start.sh` HEALTH_TIMEOUT_SECONDS already 300 (preserved from v2.0) — none of the eight new migrations approach the limit but kept the cushion.
- `backend/config.py` Settings model picks up `extra="ignore"` so an unused `BACKEND_PORT=…` (or any future stray env var) in `.env` no longer fails app startup. Found during Phase A test runs.
- `app/login/page.tsx` page-export rule violation — Next.js App Router rejects non-default exports on page files. Extracted `AuthShell` and `Field` to `frontend/components/AuthShell.tsx`.
- `UserMenu` was stale after login because the layout-level component didn't refetch `/auth/me` after the form POST. Added `AUTH_CHANGED_EVENT` dispatched by login/logout; `useAuth` listens.
- SQLAlchemy `Base.metadata` name collision on the audit log model: column is declared `audit_metadata = Column("metadata", JSON, ...)` — Python attr `audit_metadata`, SQL column + JSON payload key stay `metadata`.
- JSON column mutation invisibility: setting `users.tour_state[tour_id] = N` in-place wasn't picked up by SQLAlchemy's change-tracker — reassigning the dict wholesale (`row.tour_state = {**row.tour_state, tour_id: N}`) makes it durable. Documented in `useDriverTour` callsite comment.
- Alembic `CommandError: Could not determine revision id` on the 0011 stub file — empty revision module crashed alembic on chain walk. Turned the stub into a real no-op revision (`revision = "0011a_placeholder"`).

### Decisions

- **Two-column identity split (email + user_id).** Lets users choose a custom handle without touching the 9 pre-existing user-scoped tables that key on `user_id VARCHAR(100)`. Email is the credential; user_id is the foreign-keyable identifier the rest of the app already uses.
- **Versioned per-tour state via JSON map** (not per-tour boolean columns). Adding a new tour later = one new JSON key, no migration. Bumping a tour's version re-fires it for everyone whose stored value is lower; bump only when STEPS materially changes.
- **Server-side tour state, no `localStorage`.** Single source of truth, cross-device sync, survives browser-data clears.
- **Last-admin protection on role and status changes** — refuses to demote or suspend the only admin. Avoids accidental admin lockout.
- **Custom in-memory rate-limit middleware, not `slowapi`.** Started with slowapi per the original plan but its decorator broke FastAPI's pydantic body-parameter introspection (every POST with a body model 422'd with `loc=["query","body"]`). Rewrote as middleware; dropped the dep entirely.
- **`driver.js`, not `react-joyride`.** react-joyride 2.x imports React-18-only APIs (`unmountComponentAtNode`, `unstable_renderSubtreeIntoContainer`) that React 19 (Next 16) dropped — webpack build failed, no stable react-joyride 3.x. driver.js is ~5KB vs ~80KB, imperative API, React-version-agnostic.
- **Topic deletion does NOT cascade to subscribers' content.** Subscription row stays; scope filter just stops returning the topic. Allows owner-flip-private as a soft removal.
- **`AGENTS.md` left FriendZone-scoped intentionally** — the playbook structure is what matters; Daily Scholar conventions get a separate file in a follow-up so the FriendZone version stays a working reference.

### Operations

- **Migrations applied automatically on startup** via `create_tables()` → `alembic upgrade head`. Order: 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 (then no-op 0011a_placeholder).
- **Bootstrap admin** after first deploy: `python scripts/create_admin.py --email <you> --password <pw>`. From inside the backend container if running compose: `docker compose exec backend python scripts/create_admin.py ...`.
- **New env vars (production should NOT set these):**
  - `OPEN_SIGNUP=1` — skips invite-code requirement; dev / CI only.
  - `RATE_LIMIT_DISABLED=1` — bypasses rate limiter; dev / CI only.
  - `CSRF_DISABLED=1` — bypasses CSRF check; dev / CI only.
- **`SESSION_COOKIE_SECURE`** auto-derives from `debug` (Secure in prod, plain in dev). Override only if you know why.
- **New pip deps**: `passlib[bcrypt]>=1.7.4,<2`, `bcrypt>=4.0,<5`.
- **New npm dep**: `driver.js@^1.6.0`. (slowapi added and removed in the same release; net-new is just driver.js.)
- **No new GitHub Actions secrets.** Railway deploy matrix unchanged from v2.0.
- **Backfill expectations:**
  - Existing topics → `owner_user_id NULL` + `visibility 'public'` so Grace's praxis topics stay visible to every account.
  - Existing users → `onboarded true` (admins don't get bounced through the wizard) but `tour_state '{}'` (they'll see each tour once on next visit to its page; suppress with `UPDATE users SET tour_state = '{"dashboard":1,"scope":1,"topics":1}'` post-migration if undesirable).
- **Local dev**: host postgres on :5432 collides with the docker postgres service — `docker-compose.yml` postgres port changed to `5433:5432` so the host port is free.

### Followups

- Email verification + email-driven password reset (currently locked-out users have to ask an admin out-of-band). Needs email infra — separate project.
- `must_change_password` flag set by admin reset so the temp password forces a change on next login.
- Per-session "Active devices" UI so users can revoke individual sessions instead of all-other.
- DiscoverTour on `/topics/discover` introducing the subscribe model (one more `useDriverTour` component + one KNOWN_TOUR_IDS entry).
- Redis-backed rate limiting once we scale beyond one backend process.
- CSRF path-exempt list when webhook receivers land.
- Tour analytics ("which step did users drop off?") if usage data matters.
- Adapt `AGENTS.md` for Daily Scholar's stack (current content is Flask social-network).
- iPhone hardware verification of v2.1 mobile nav still pending.

## [v2.1] — 2026-06-25

Mobile-navigation release. One PR (#35) replaces the overflowing six-item horizontal top nav with a mobile-only bottom tab bar (Home / Papers / Topics / Quiz / More), makes the dashboard rows (stats band, section tabs, paper / topic-review / quiz action bars) responsive so they stop laying out wider than the viewport, and adds an `html, body { overflow-x: hidden }` safety net so any future stray-width child can't reintroduce horizontal pan. Frontend-only release. Desktop layout (≥ `md`) byte-equivalent to v2.0. 5 files changed, +262 / −45. No migrations; no new env vars; no new dependencies.

### Added

#### Mobile bottom tab bar component (PR #35)

- New `frontend/components/MobileTabBar.tsx` — `'use client'` component. Renders a five-tab bar fixed to the bottom of the viewport at `md:hidden`: Home (`/`), Papers (`/papers`), Topics (`/topics`), Quiz (`/quiz`), and More. Each tab is a Next.js `<Link>` with `aria-current="page"` set when active; the active tab gets a `text-blue-600` color plus a 6×0.5px indicator pill positioned at `top-1.5`.
- Active-tab resolution uses `usePathname()` + a per-tab `match(pathname)` predicate (Home matches `pathname === '/'`, the others match their `startsWith(prefix)`). Routes not claimed by a tab (`/settings/*`) light up "More" as active via `activeTabIdx === -1`.
- Tapping "More" opens a bottom sheet (`role="dialog" aria-modal="true" aria-label="More menu"`) anchored to `bottom: 0`. Sheet contains two links — Settings → `/settings/scope`, and API Docs → `${API_BASE}/docs` (external, `target="_blank" rel="noopener noreferrer"`). A drag-handle div, an `<h2>More` header, and a close-button are included for affordance.
- Sheet lifecycle:
  - Opens on More-tab tap (`setMoreOpen(true)`).
  - Closes on route change (`useEffect` on `pathname` → `setMoreOpen(false)`).
  - Closes on `Escape` keypress (`useEffect` adds a window keydown listener while open, removes on cleanup).
  - Closes on scrim tap (scrim is a full-screen `<button aria-label="Close menu">` over the page at `z-50`, behind the sheet).
- iOS PWA respect: the bottom bar's `paddingBottom` style is `env(safe-area-inset-bottom)`; the sheet's `paddingBottom` is `calc(env(safe-area-inset-bottom) + 1.25rem)`. Both clear the iOS home indicator when the PWA is installed to the home screen.

#### Local cowork workspace folder excluded from git (PR #35)

- `.gitignore` gains a `daily scholar/` entry (note the space — that's the actual folder name the cowork agent mounts inside the repo when this user runs sessions in the daily-scholar working directory). Mirrors the existing pattern for `pr-scripts/`, `PUBLIC_REPO_AUDIT.md`, and `PWA_MIGRATION_PLAN.md` — kept on disk for reference but never committed. Design explorations (the four-option mobile-nav mockup HTML from this PR) live there.

### Changed

#### `frontend/app/layout.tsx` — split nav by viewport (PR #35)

- The existing horizontal nav-links row inside the `<nav>` block (Dashboard, Papers, Topics, Quizzes, Settings, API Docs) is now `hidden md:flex` instead of `flex`. On mobile the top bar collapses to just the logo (`📚 Daily Scholar`); the six links go away.
- `<MobileTabBar />` is mounted globally at the body level (between `<footer>` and `<AuthBoundary />`). It self-hides at `md:hidden`, so desktop never renders it.
- `<main>` gets `pb-24 md:pb-8` (previously `py-8`). The `pb-24` reserves 96px of clearance for the fixed bottom bar (64px bar + safe-area + breathing room); desktop falls back to the normal py-8.
- `<footer>` gets `hidden md:block` (previously `block`). The textual footer would otherwise be obscured by the fixed bar on mobile and is redundant given the tab bar's persistent presence.
- New `import MobileTabBar from "@/components/MobileTabBar"`.

#### `frontend/app/page.tsx` — responsive dashboard rows (PR #35)

- **Stats band** (the streak / papers seen / archived / quiz accuracy row at the top of the dashboard): inner wrapper changed from `<div className="flex items-center justify-between flex-wrap gap-4">` with a nested `<div className="flex items-center gap-6">` over the four stat blocks → `<div className="grid grid-cols-2 gap-3 md:flex md:items-center md:justify-between md:flex-wrap md:gap-4">`. Each stat block gets `min-w-0 truncate` so a long localized label can't push the band wide. "Best: N days" gets `col-span-2 md:col-auto` so it spans both mobile columns and aligns right on desktop.
- **Section tabs (Today's Paper / Topic Review / Quiz)**: wrapper changed from `<div className="flex gap-2 border-b border-slate-200 pb-2">` → `<div className="grid grid-cols-3 gap-1 md:flex md:gap-2 border-b border-slate-200 pb-2">`. Each button gets `flex items-center justify-center gap-1.5 px-2 py-2 md:px-4 ... text-sm md:text-base ... min-w-0`. Button labels are abbreviated on mobile via responsive spans — `<span className="hidden md:inline">Today's </span>Paper`, `<span className="hidden md:inline">Topic </span>Review`. The label `<span>` is `truncate`; the badge / dot gets `flex-shrink-0` so it never pushes the label off the button.
- **Paper action bar** (the `border-t` footer of the paper card holding Open + PDF on the left and New paper + Save to Archive on the right): wrapper changed from `flex items-center justify-between` → `flex flex-col gap-2 md:flex-row md:items-center md:justify-between`. Right-side action group gains `flex-wrap` so a long button label can wrap to two lines instead of overflowing.
- **Topic review header** (course badge + topic name on the left; New + Save buttons on the right): wrapper changed from `flex items-center justify-between mb-4` → `flex flex-col gap-3 mb-4 md:flex-row md:items-start md:justify-between`. Title block gets `min-w-0`; the topic-name `<h2>` gets `break-words`; the action group gains `flex-wrap`.
- **Quiz header** (Knowledge Check metadata + Save Results + New Quiz): wrapper changed from `flex items-center justify-between` → `flex flex-col gap-3 md:flex-row md:items-center md:justify-between`. Action group gains `flex-wrap`.

#### `frontend/app/globals.css` — horizontal-scroll safety net (PR #35)

- Added a four-line rule after the existing `body { font-family: ... }` block: `html, body { overflow-x: hidden; max-width: 100vw; }`. Annotated with a comment explaining the dual motivation — clip rogue stray-width children, and remove the failure mode where an accidental horizontal swipe near the bottom of the screen lands on the fixed tab bar's "More" tab.

### Decisions

#### Bottom tab bar over four other patterns considered

The mobile-nav exploration produced four phone-frame mockups (Dashboard + dropdown / bottom tab bar / hamburger drawer / icon rail). Bottom tab bar was chosen because primary destinations sit at thumb reach with one tap each, it matches user expectation for an installed PWA on iOS, and it absorbs the overflow problem without requiring abbreviated copy on desktop. The mockup HTML lives under the cowork session workspace folder (gitignored as of this release); keep it locally if you want to revisit the alternates.

#### Horizontal-scroll clipping over revealing

`html, body { overflow-x: hidden }` will clip any genuinely-overflowing content instead of revealing it on horizontal scroll. The tradeoff is intentional — a fixed bottom tab bar plus a horizontal scroll surface is a UX trap where every horizontal swipe risks firing a stray tab, and clipping pushes the bug fix upstream (whoever introduces the wide child will see clipping in dev and fix it). If a future dashboard needs a wide-table layout, wrap the table in its own `overflow-x-auto` container — the rule on `body` doesn't propagate through nested scroll containers.

### Operations

- **No env-var changes.** Carrying forward the v2.0 matrix: `NEXT_PUBLIC_API_URL` (frontend build arg, hard-fails at build time if missing), `CORS_ALLOWED_ORIGINS` (backend CORS allowlist), `CF_ACCESS_VERIFY_JWT` family (optional, off by default), `LLM_TASK_*` routing knobs.
- **No new GitHub Actions secrets.** The Railway token + service-ID matrix is unchanged.
- **No deploy choreography.** Frontend rebuilds and ships; backend is untouched. Cloudflare Access topology unchanged (still requires the single-Access-app-per-environment bundling from v2.0).
- **Tag + GitHub Release after merge.** `git tag -a v2.1 -m "v2.1 — mobile bottom tab bar"`; `git push origin v2.1`; copy `docs/releases/v2.1.md` (or the highlights paragraph) into a new GitHub Release tied to the tag.

### Followups captured during the phase

- **Physical iPhone verification still pending.** Mobile changes were verified in a desktop browser at narrow widths (375 × 720) and pass `npx tsc --noEmit` clean, but `env(safe-area-inset-bottom)` behavior under the home indicator hasn't been observed on hardware yet. Worth a quick check on an installed PWA before promoting to the broader beta cohort.
- **Other pages may still overflow.** Only `app/page.tsx` (dashboard) got per-row responsive fixes. `/papers`, `/topics`, `/quiz`, and `/settings/scope` may still have `justify-between` rows that lay out wider than the viewport on mobile. The `globals.css` safety net keeps them usable (anything that would have overflowed gets clipped), but each page should get the same row-by-row treatment as the dashboard. Low priority — the safety net buys time.
- **Badges on the bottom tab bar.** The in-page section tabs already render small dot / count badges for new content (e.g., topic-review count, quiz question count). The bottom tab bar doesn't yet — would be a useful affordance for surfacing unread daily content. Requires `getDailyContent` to be callable from a layout-level component (it's currently called from the dashboard page).
- **Settings depth.** "More → Settings" lands on `/settings/scope`. As `/settings/notifications`, `/settings/topics`, `/settings/push-debug`, `/settings/account` etc. land, the "More" sheet should grow into a proper grouped menu instead of two flat rows. Not urgent — revisit at ~4 entries.

---

## [v2.0] — 2026-06-25

Setup-audit release. Three PRs (#30 README split, #32 setup audit, #33 CI workflow fix) close out everything that was making prod deployment fragile. **Multi-origin CORS** replaces the single-`FRONTEND_URL` trap; **frontend Dockerfile hard-fails** when `NEXT_PUBLIC_API_URL` is empty at build time (so the silent localhost fallback can't bake into a prod bundle); **LLM-failure cache-poisoning defense** stops a swallowed Gemini exception from locking the Topic Review tab on an empty card for 24h; **CI deploy workflow** uploads the repo root for both services (was `cd`'ing into `frontend/` and conflicting with the Railway service's `Root Directory=/frontend` dashboard setting); **README split** pulls 818 lines of monolith into four focused docs under `docs/`. No migrations. Schema unchanged from v1.1's `0003_auth_ready_user_id`.

### Added

#### CORS allowlist with multi-origin support (PR #32)

- New `cors_allowed_origins: Optional[str]` setting on `backend/config.py`. Comma-separated list. When set, REPLACES the single-origin `FRONTEND_URL`-derived allowlist; otherwise the existing behavior (`FRONTEND_URL` + `http://localhost:3000` + `http://127.0.0.1:3000`) is preserved for back-compat.
- New `_resolve_cors_origins()` helper in `backend/main.py`: splits the comma-list, strips surrounding whitespace + trailing slashes, dedupes via a `set`, drops empties. Returns the final list to `CORSMiddleware(allow_origins=...)`. The trailing-slash strip is load-bearing — `credentials: 'include'` requires byte-for-byte origin match and a trailing slash on either side silently rejects the request.
- `.env.example` gains a `CORS_ALLOWED_ORIGINS=` example with prod-mode value comment + a "FRONTEND BUILD-TIME CONFIG (Next.js)" section documenting `NEXT_PUBLIC_API_URL=https://api.daily-scholar.com` for production.

#### LLM-failure visibility + cache-poisoning defense (PR #32)

- `backend/services/content_generator.py` LLM-calling methods (`generate_paper_summary`, `generate_topic_review`, `generate_quiz_questions`) gained `traceback` imports + improved exception logging: `[content_generator] <task> failed: {type(e).__name__}: {e}` followed by `traceback.print_exc()`. Previously the print was `f"Error generating <task>: {e}"` — many exception classes (notably the Google `genai` SDK's `ServerError`) stringify to nothing useful, so 503 / 429 / quota-exceeded failures were genuinely invisible in container output.
- `generate_paper_summary` + `generate_topic_review` mark failures with a `__generation_failed__: "<ClassName>: <message>"` sentinel on the returned dict alongside the existing empty-string fallback fields.
- `backend/services/daily_content.py` (in the `need_review` branch around the `_select_topic_from_scope` call) now checks `review.get("__generation_failed__")` before appending to `topic_reviews`. If set, logs `[daily_content] skipping cache for failed topic review on <topic_id>: <error>` and skips the append. The empty list then trips the existing `len(cached_topic_reviews) == 0` cache-invalidation check on the next request, forcing a retry instead of locking the user in an empty-card state until tomorrow's regen.

#### Build-time NEXT_PUBLIC_API_URL hard-fail (PR #32)

- `frontend/Dockerfile` builder stage gained a `RUN if [ -z "$NEXT_PUBLIC_API_URL" ]; then ...; exit 1; fi` check after the `ARG`/`ENV` declaration. Error message points at the Railway service-vars step + `frontend/railway.toml` for context. Previously the build silently inlined the `lib/api.ts:7` fallback `http://localhost:8000` whenever the build arg didn't propagate — every visitor's browser then tried to fetch their own machine.
- `frontend/railway.toml` gained a "REQUIRED service Variables" section at the top of the file documenting `NEXT_PUBLIC_API_URL = https://api.daily-scholar.com` with rationale (build-time inlining, automatic Railway forwarding when the Dockerfile declares the ARG).

#### Docs split into focused files (PR #30)

- `README.md` rewritten as a fork-first quickstart (~64 lines, down from 818). Deep-links into the new `docs/` files for everything operational.
- `docs/API.md` — full endpoint reference covering paper discovery, topic CRUD, archive, quiz, daily content, push, user scope. Per-endpoint method + path + auth requirements + request/response shape.
- `docs/ARCHITECTURE.md` — runtime topology (FastAPI + APScheduler + Postgres + Next.js + B2), the unified Topic model + bootstrap-from-YAML flow, the daily-content cache invalidation flow, the storage abstraction (`LocalStorage` vs `B2Storage`), the auth resolution order.
- `docs/DEPLOY.md` — Railway-specific setup walkthrough: project + service creation, env-var matrix per service per env, Cloudflare Access bundling, the `deploy.yml` workflow's expected GitHub secrets.
- `docs/PWA.md` — service-worker registration story, push subscription lifecycle, install-prompt rules, the `disable: process.env.NODE_ENV === "development"` decision in `next.config.js`.

### Changed

#### Frontend localhost hardcodes removed (PR #32)

- `frontend/lib/api.ts:7` — `const API_BASE` is now `export const API_BASE` so other modules (notably `app/layout.tsx`) can reuse the same value without re-implementing the `NEXT_PUBLIC_API_URL || 'http://localhost:8000'` fallback.
- `frontend/app/page.tsx` — quiz answer submission switched from a hardcoded `fetch('http://localhost:8000/quiz/answer?...')` (with no `credentials: 'include'`) to the shared `submitAnswer(questionId, answer)` helper from `lib/api.ts`. The shared helper goes through `fetchAPI()`, so it picks up `credentials: 'include'`, the JSON `Content-Type` header, and the 401 boundary (`AuthError` + `daily-scholar:auth-error` event dispatch) for free.
- `frontend/app/layout.tsx` — API Docs nav link uses `${API_BASE}/docs` instead of the hardcoded `http://localhost:8000/docs`. Imports `API_BASE` from `@/lib/api`.

#### docker-compose.yml frontend build-arg propagation (PR #32)

- `frontend.environment.NEXT_PUBLIC_API_URL: http://localhost:8000` moved to `frontend.build.args.NEXT_PUBLIC_API_URL: http://localhost:8000`. Inline comment explains why: `next build` inlines the value at build time, not container start, so a runtime `environment:` value would be too late. The Dockerfile's new hard-fail check requires the build arg to be present.
- Backend service unchanged.

### Fixed

#### CI deploy workflow uploads repo root for frontend too (PR #33)

- `.github/workflows/deploy.yml` removed the per-service `WORKDIR` branching (which set `WORKDIR="frontend"` for the frontend matrix leg, `WORKDIR="."` for backend). Both services now use `WORKDIR="."` — the workflow uploads the entire repo for both `railway up` invocations.
- Symptom: every git-triggered frontend deploy failed with "deployment was triggered manually without git source context, so the snapshot contained no repository files and the builder could not find the /frontend root directory." The Railway dashboard attributed the deploy to "Grace O'Malley" via the CLI, masking that it was actually the GitHub Actions runner using her Railway token — diagnostics took several rounds to triangulate.
- Root cause: the Railway frontend service has `Root Directory = /frontend` configured in the dashboard. When the workflow `cd`'d into `frontend/` and ran `railway up`, the uploaded snapshot's root WAS `frontend`, and Railway then applied the `/frontend` root_directory on top, looking for `frontend/frontend/Dockerfile` (which doesn't exist).
- Inline comment in `deploy.yml` documents the rationale so the next person doesn't reintroduce the `cd`.

### Decisions

#### No migration in this release

Schema is unchanged from v1.1's `0003_auth_ready_user_id`. Every code change in v2.0 is either configuration, error-handling-on-the-existing-payload, build/CI plumbing, or documentation. Existing Postgres + SQLite installs upgrade in place with no `alembic upgrade head` step needed beyond what's already applied.

#### Hard-fail over silent fallback on the frontend build

The frontend Dockerfile change is intentionally aggressive — a missing `NEXT_PUBLIC_API_URL` now fails the build with `exit 1`, where it previously produced a working-looking image that quietly fetched `http://localhost:8000` from every visitor's browser. The tradeoff is that anyone running `docker build` directly (without the `--build-arg`) now has to set the variable explicitly even for local-mode test images. `docker compose up --build` flows through the new `build.args` block automatically, so the local-dev path stays smooth. This burned prod twice during the v1.1 → v2.0 work; making it impossible to recur was worth the slight ergonomic cost.

### Operations

- **New env vars to set in Railway before the next deploy:**
  - Backend (dev + prod): `CORS_ALLOWED_ORIGINS=https://scholar-dev.daily-scholar.com` / `https://scholar.daily-scholar.com` respectively.
  - Frontend (dev + prod): `NEXT_PUBLIC_API_URL=https://api-dev.daily-scholar.com` / `https://api.daily-scholar.com` respectively. **The build will hard-fail without this** — set before merging or the next deploy errors at image-build time.
- **Cloudflare Access topology** must bundle frontend + backend hostnames under a single Access application per environment (`scholar-dev` + `api-dev` for dev; `scholar` + `api` for prod). Two separate apps means the session cookie doesn't ride along cross-host and every API call gets a login redirect (manifests as a misleading CORS error). See `docs/DEPLOY_CLOUDFLARE.md`.
- **Existing local-mode `.env` may need a `gemini-3.5-flash` → `gemini-2.5-flash` typo correction** if you copied an early LLM_TASK_* override. The v2.0 cache-poisoning defense will now surface the underlying 503 via the new logging instead of locking the Topic Review on an empty card, but you'll still see the failure until the model name is corrected.
- **No new GitHub Actions secrets.** Existing `RAILWAY_TOKEN_{DEV,PROD}` + `RAILWAY_{BACKEND,FRONTEND}_SERVICE_ID_{DEV,PROD}` matrix from v1.1 is unchanged.

### Followups captured during the phase

- **Admin role gate** — `/admin/*` endpoints have no in-app role check; gated only by Cloudflare Access. Don't open `/admin/*` to the beta cohort until a role/group gate lands.
- **Cache-poisoning defense for `generate_paper_summary`** — the sentinel + skip-cache pattern from v2.0 is only wired for topic reviews. Extending to paper summaries is straightforward but lower priority because the cache invalidation key (`cached_paper is None`) doesn't lock the UI the same way the topic-review one did.
- **`make compose-up` shortcut** — the Makefile only covers local-mode (venv + `start.sh`). A compose target would help beta testers exercise the Docker path without memorizing the command.
- **`docker build` direct-invocation guidance** — the hard-fail change means anyone running `docker build` outside `docker compose` needs to know to pass `--build-arg NEXT_PUBLIC_API_URL=...`. Worth a paragraph in `docs/DEPLOY.md` once the first tester trips on it.

---

## [v1.1] — 2026-06-20

Auth-readiness + first prod-on-Railway pass. Hybrid Cloudflare Access pattern (email header always-on; JWT verification env-gated by `CF_ACCESS_VERIFY_JWT`), three migrations bringing `user_id` scoping to nine tables, Phase 5 beta-flow preservation (`setup.sh` / `start.sh` / Makefile), Dockerfile + Railway deploy fixes, and a string of stability bugfixes for the public-repo launch. Three migrations total over v1.0's baseline.

### Added

- **Phase 4 — auth identity (PR #14, #15).** Hybrid CF Access pattern shipped: `get_current_user_id` reads `Cf-Access-Authenticated-User-Email` when present (Layer 1, always on), optionally verifies `Cf-Access-Jwt-Assertion` against the team JWKS when `CF_ACCESS_VERIFY_JWT=1` (Layer 2). When both layers are on and both headers are present, the JWT email claim must match the header (blocks mix-and-match attacks). Solo fallback to `'__local__'` sentinel preserved. PyJWT is a lazy import. All endpoints touching the nine user-scoped tables (`seen_papers`, `archived_papers`, `archived_quizzes`, `archived_topic_reviews`, `paper_pdfs`, `daily_content_cache`, `user_stats`, `push_subscriptions`, `user_settings`) require `user_id: str = Depends(get_current_user_id)` and filter every query by `user_id`. `scripts/reassign_user_id.py` migrates rows from one `user_id` to another across all nine tables. New `AuthBoundary` React component listens for the `daily-scholar:auth-error` global event and shows a re-auth banner.
- **Phase 5 — beta-flow preservation (PR #16, #17).** `setup.sh` (one-shot local install), `start.sh` (launch backend + frontend, wait for `/health`), Makefile shortcuts (`setup`, `start`, `backend`, `test`, `clean`, `migrate`, `vapid`). README + topic-config docs split for first-time beta testers. SQLite + local-filesystem path stays runnable with no Railway / B2 / Cloudflare dependency.
- **`docs/refresh-readme` (PR #23).** README refreshed for fork-first framing + current architecture.

### Changed

- **`PORT` env var renamed to `BACKEND_PORT` for local-dev** to avoid collision with Next.js's `PORT` in `make start`. Inside the Docker container, `PORT` is still honored (Railway-canonical).

### Fixed

- **`fix(llm): drop temperature param for Claude models that reject it` (PR #28).** New `_NO_TEMPERATURE_MODEL_PREFIXES` tuple in `anthropic_client.py` listing model prefixes that reject `temperature` (Opus 4.x, Sonnet 4.6). `complete()` only attaches `temperature` to the request kwargs when the current model accepts it. Older models (Sonnet 4.5, Haiku 4.5) still get the temperature passed.
- **`fix(frontend): send credentials cross-origin so CF Access cookie rides along` (PR #26).** `fetchAPI` in `lib/api.ts` now sets `credentials: 'include'` on every request. Without it the browser drops the `.daily-scholar.com` parent-domain CF Access cookie on cross-origin API calls and Access 302s every request to its login page, which CORS then blocks.
- **`fix(frontend): accept NEXT_PUBLIC_API_URL as build arg` (PR #24).** First version of the build-arg plumbing in `frontend/Dockerfile`. v2.0 layered the hard-fail check on top.
- **`fix(deploy): use $PORT (Railway-canonical) in Dockerfile` (PR #18).** Backend Dockerfile CMD switched to `sh -c "uvicorn ... --port ${PORT:-8000}"` so Railway's runtime `$PORT` injection works. Railway doesn't shell-expand `${PORT}` in `railway.toml`'s `startCommand` field, so the previous form broke uvicorn.
- **`fix(migration): make 0003 idempotent for half-applied beta DBs` (PR #19).** Migration `0003_auth_ready_user_id.py` is now safe to re-run against DBs where a previous attempt partially applied. `op.add_column` calls guarded by `column_exists` inspection.
- **`fix(dev): reap uvicorn/Next.js reload workers on shutdown` (PR #20).** `start.sh` cleanup trap kills descendant processes via `pkill -TERM -P`, escalates to `SIGKILL` after a 5s wait. Previously the parent process was killed but the `--reload` / `npm run dev` workers lived on, holding the SQLite lock + the dev-server ports.
- **`fix(discovery): tighten per-call timeout on flaky paper sources` (PR #21).** Per-source timeout on CORE API + Semantic Scholar lookups in `paper_discovery.py`. Previously a single slow upstream blocked the whole daily discovery cycle.

### Migration shape

Three migrations from v1.0's baseline. Apply in order via `alembic upgrade head`:

1. `0001_baseline.py` — pre-v1.0 schema captured as the alembic baseline (no DDL emitted; `op.execute(...)` no-ops). Stamps the DB at `0001`.
2. `0002_topics_user_settings_push.py` — unified `topics` table replacing `interests` + `courses` split; `user_settings` for the scope selector (silo / multi / all); `push_subscriptions` for Web Push fanout.
3. `0003_auth_ready_user_id.py` — `user_id` column added to the nine user-scoped tables. Default value `'__local__'` for existing rows. Idempotent (PR #19).

### Configuration

- **New env vars (auth):** `CF_ACCESS_VERIFY_JWT`, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD_TAG` — all blank by default, JWT verification off. Solo + beta deployments unchanged.
- **New env vars (storage):** `STORAGE_BACKEND=local|b2`, `LOCAL_STORAGE_ROOT=./data`, plus the `B2_*` family for B2 backend.
- **New env vars (push):** `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. Push endpoints 503 until set.
- **New env vars (LLM routing):** `LLM_TASK_SUMMARY`, `LLM_TASK_REVIEW`, `LLM_TASK_QUIZ`, `LLM_TASK_EVALUATE`, `LLM_TASK_DEFAULT` — per-task `provider:model` overrides. Empty = defaults from `factory.py`.

---

## [v1.0] — 2026-06-15

Initial public-repo release. PWA shell, Web Push (VAPID + pywebpush), Phase 0 topic model + praxis config, multi-provider LLM client interface (Anthropic + Gemini + Antigravity), Backblaze B2 storage abstraction, Railway + Cloudflare deployment plumbing. Tagged as `v1.0` after Phase 0–3 of the PWA migration plan landed.

### Added

- FastAPI backend with paper discovery (arXiv + CORE + Semantic Scholar), topic-review + quiz generation via Claude, archive management.
- Next.js 16 PWA frontend with Serwist service worker, install prompt, push subscription lifecycle.
- Unified `Topic` model with paper-discovery + learning-content fields, stored as `config/topics/*.yaml` + a `topics` DB table. DB is canonical; YAML is bootstrap + export.
- Multi-provider LLM router with per-task routing knobs.
- Backblaze B2 storage backend (S3-compatible) with `LocalStorage` fallback for solo / beta deployments.
- APScheduler nightly daily-content generation job.
- Cloudflare Access compatible (email-header trust mode at v1.0; JWT verification arrived in v1.1).
