# Future Features

Tracker for substantial features under consideration for Daily Scholar. Not a backlog — small bugs and polish go in GitHub Issues. This file is for things that need scoping conversation before they're issue-ready: where the architectural shape, dependencies, or open questions matter more than the line-by-line work.

**Status legend:**

- **proposed** — captured here; no scoping done yet.
- **scoping** — actively shaping the design; open questions being resolved.
- **scheduled** — scoped + sequenced; landing in a named release.
- **in-progress** — branch open.
- **deferred** — explicitly paused with a gating condition documented.
- **shipped** — done; entry kept for one release as historical pointer, then moved to `CHANGELOG.md` and deleted from here.

---

## Auth + identity

### Login interface · proposed

In-app login UI replacing or augmenting the Cloudflare Access gate.

**Why.** Cloudflare Access works for the closed beta cohort (~30 users on the free tier, email-policy gated), but it's a deal-breaker for the wider audience: every new tester needs me to add their email to the Access policy, and the CF Access login flow has its own UX that bears no relation to Daily Scholar's. A native login lets users self-serve onboarding (with invite codes or open registration, TBD) and gives me a place to surface user-facing settings that don't fit Access (display name, push prefs, etc.).

**Scope (in).**

- Email + password registration + login, password hashing via `passlib[argon2]`.
- Session management — cookie-based with a secure HttpOnly session cookie, NOT JWT (avoids needing a refresh-token dance for a personal-scale app).
- `/auth/login`, `/auth/register`, `/auth/logout`, `/auth/forgot-password` Next.js pages.
- New `User` SQL model with `id` (replacing the `__local__` / email-header sentinel pattern), `email`, `password_hash`, `display_name`, `created_at`, `last_login_at`, `is_active`. Existing nine user-scoped tables migrate their `user_id` columns from string to FK on the new `users.id`.
- Migration helper: `scripts/migrate_email_user_ids_to_users_table.py` — for every distinct `user_id` in the existing nine tables, INSERT a corresponding `users` row (password_hash NULL → user must reset before next login), then rewrite all FKs.

**Scope (out — defer to followups).**

- OAuth (Google / GitHub / Apple Sign-In). Captured separately under [OAuth providers · proposed](#oauth-providers--proposed) (which doesn't exist yet; promote when this lands).
- Email verification flow. Initial release lets users register without verifying email; verification ships in a followup.
- Magic-link login. Strictly password to start.
- TOTP / WebAuthn second factor.

**Open questions.**

- **Coexist with Cloudflare Access, or replace it?** Coexist (CF Access at the edge + native login behind it) gives belt-and-braces but is a confusing double-login UX. Replace (turn off CF Access, native login is the only gate) is cleaner but means the origin firewall becomes the only barrier between the public internet and the backend — needs solid rate limiting on `/auth/*` and a more aggressive lockout policy than the current "trust CF Access" posture justifies. Lean: replace, with CF as a CDN/WAF layer (rules-only, not Access).
- **Invite-only or open registration?** Beta cohort suggests invite-only with a code minted by an admin (`flask invite create` analog). Public release could relax. Mirror the FriendZone invite-request flow if needed.
- **Password reset transport.** SMTP via an existing provider (Resend / Postmark / SES)? Adds a new env var pair + a dependency. Lean: Resend (`resend-python`), free tier covers personal-scale.

**Dependencies.**

- New backend deps: `passlib[argon2]`, `itsdangerous` (signed session tokens), `resend` or chosen email SDK.
- New env vars: `SESSION_SECRET_KEY` (Fernet-rotatable), `SMTP_*` or `RESEND_API_KEY`, `REGISTRATION_MODE` (`open|invite_only`).
- New migration. The `user_id` → `users.id` FK rewrite is the load-bearing piece; everything else is additive.
- Coordinated with [Admin controls · proposed](#admin-controls--proposed) — the admin gate becomes practical only once users are first-class.

---

## Admin + ops

### Admin controls · proposed

In-app admin role + a small admin UI for the operations that today require shell access or direct DB writes.

**Why.** `/admin/*` endpoints exist server-side but have no in-app role check — they're gated only by Cloudflare Access (per the existing memory: "don't open `/admin/*` to the beta cohort until a role/group gate lands"). Plus a handful of recurring ops chores (cache bust, force topic regen, re-bootstrap topics from YAML, view user activity for debugging) currently require me to SSH or `flask shell` against the prod DB, which is slow and easy to typo.

**Scope (in).**

- `users.role` column (`'user' | 'admin'`, default `'user'`). Seeded admins via `flask admin grant <email>` CLI.
- New `require_admin` FastAPI dependency that wraps `get_current_user_id` and 403s on non-admin. Applied to every existing `/admin/*` endpoint.
- New Next.js admin pages under `/admin/`:
  - `/admin/users` — list, search by email, view per-user stats, soft-disable (`is_active=False`).
  - `/admin/topics` — bulk re-bootstrap from YAML, force YAML export, view orphaned topics.
  - `/admin/cache` — bust today's `daily_content_cache` for one user or globally; surface the most recent failure logs (the `__generation_failed__` sentinel exposes the exception class).
  - `/admin/stats` — system-wide counts (papers seen / archived, quizzes taken, push subscriptions active), recent errors from container logs.
- Admin-only nav surface in the existing top bar, only rendered when `currentUser.role === 'admin'`.

**Scope (out — defer to followups).**

- Audit log of admin actions (who did what when). Mention in followups; add if admin headcount ever exceeds one.
- Multi-tenant admin (organization-scoped admins vs. system admins). Premature for the foreseeable cohort size.
- Impersonation / "view as user" mode. Useful for debugging but a sharp security primitive; defer until specifically needed.

**Open questions.**

- **Does this require [Login interface](#login-interface--proposed) to ship first?** Yes — there's no notion of "this user is an admin" without a `users` table. Sequence accordingly.
- **Should admin actions fire push notifications to the affected user (e.g., "an admin disabled your account")?** Probably not for v1; admins acting on users is a sensitive interaction and the right UX isn't obvious. Capture as a followup if it comes up.

**Dependencies.**

- Blocked by [Login interface · proposed](#login-interface--proposed) — `users.role` requires the `users` table.
- Same migration / sequencing as the login work; can land in the same release.

---

## Engagement + notifications

### Push notifications surface · proposed

Bring the server-side Web Push primitive (already shipped: VAPID + pywebpush + `push_subscriptions` table + service-worker registration in Serwist) to a user-managed UI surface, plus the scheduled daily-content push.

**Why.** The plumbing exists end-to-end but there's no UI for users to opt in / out, no per-event-type granularity, and no scheduled trigger that fires the daily push when new content lands. The current state is "the code can send push, nothing actually does."

**Scope (in).**

- **Subscription UI.** New `/settings/push` page in the frontend with a single "enable push" toggle that calls `Notification.requestPermission()` + `serviceWorker.pushManager.subscribe()` and POSTs the subscription to `/push/subscribe`. Existing endpoint returns 503 today until `VAPID_PUBLIC_KEY` is set — surface that gracefully ("push isn't configured on this deployment") instead of a generic error.
- **Per-event toggles.** New `push_preferences` columns or JSONB on `user_settings`:
  - `push_daily_paper` (default `true`) — fires when today's paper is generated.
  - `push_topic_review` (default `true`) — fires when today's topic review is generated, IF separate from the paper (currently they're combined).
  - `push_quiz_ready` (default `false`) — fires when a quiz is regenerated. Quiet by default since the user usually triggers it.
- **Scheduled push wire-up.** Hook the existing APScheduler nightly daily-content job to `send_push_to_user(user_id, payload)` for every user with `push_daily_paper=True` and at least one active push subscription. Payload: title from `DailyContent.paper.title[:140]`, deep-link to `/`. Currently the `send_push_to_user` helper exists but isn't called.
- **Subscription lifecycle hygiene.** On a push delivery returning 410 Gone (subscription expired or unsubscribed), soft-delete the row from `push_subscriptions` in the same request. Without this, dead subscriptions accumulate and slow down every fanout.

**Scope (out — defer to followups).**

- Per-topic push toggles ("notify me only when the paper matches Topic X"). Useful but requires UI for picking topics, and the scope selector already serves the same intent for paper discovery itself.
- Quiet hours / Do Not Disturb window per user. Mention in followups; add if anyone complains about 06:00 EST pings.
- Push notification grouping on iOS (multiple new-paper notifications collapsing into one). Out of scope until the per-event-type fanout actually multiplies.
- "Try a test push" button in the settings page. Nice-to-have for debugging; not load-bearing.

**Open questions.**

- **Does this require [Login interface](#login-interface--proposed) to ship first?** No — push subscriptions are already keyed by `user_id` (which today is the CF Access email or `__local__` sentinel). The scheduled-push fanout works fine against today's identity model. But: integrating with the login surface (a "manage push from your account page" link) is cleaner once Login lands.
- **iOS 16.4+ install requirement.** Web Push on iOS only works if the PWA is installed via "Add to Home Screen." Need to detect this and message clearly in `/settings/push` so iOS users on Safari-in-browser aren't confused when the toggle does nothing.
- **VAPID key rotation story.** Rotating `VAPID_PUBLIC_KEY` invalidates every active subscription (browser stores the public key when it subscribes; mismatched key = drop). Document this as a one-way operation in `docs/DEPLOY.md` and only rotate on a known-key-compromise.

**Dependencies.**

- No new env vars beyond the existing `VAPID_*` triplet.
- No new external deps (`pywebpush` already pinned).
- Migration is small: `user_settings` JSONB or three boolean columns (lean JSONB for forward-compat — adding new toggle types later is `.update()` instead of `op.add_column()`).

---

## Process notes

When promoting an entry to **scheduled**, copy it to the relevant `docs/releases/vX.md` "Coming next" section and update the status here. When promoting to **shipped**, move the substantive detail to the `CHANGELOG.md` entry for that release and leave only a one-line pointer here for one release cycle, then delete.

When deferring an entry, add a **Gating condition:** line that names the specific signal that would unblock it (e.g., "WHEN admin headcount > 1" or "WHEN a beta tester asks for it"). Don't defer without a gate — it's how the tracker stays meaningful instead of becoming a graveyard.
