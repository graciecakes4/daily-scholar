# Changelog

## [v2.9] — 2026-09-05

v2.8 split paper discovery into research tracks; this release fixes the two reasons that still didn't produce a focused feed. **Within a track, only the highest-weight topic was actually being searched** (PR #77) — keyword aggregation ran depth-first, so a topic holding more keywords than the whole budget consumed it alone, and on the real topic set `missing-modality-learning` contributed no search terms at all despite equal weight. **Topics can now declare which field they belong to** (PR #78) — a new optional `require_any` gate means a topic can hold broad method vocabulary like "conditional diffusion" without matching every discipline that shares it, which is how a brain-MRI inpainting paper had been clearing the bar in an astronomy track. **One new migration, zero new dependencies, zero new environment variables.** Full release notes in [docs/releases/v2.9.md](docs/releases/v2.9.md).

### Added

#### Optional domain gate on topics (PR #78)

- New `require_any` list on `Topic` (migration `0017_topic_require_any`). When non-empty, a paper must contain at least one of its terms before any of that topic's keywords are scored. Empty — the default, and every pre-existing row — disables it, so scoring is unchanged for topics that don't opt in.
- Matching is **whole-word**, deliberately unlike keyword matching. The gate decides whether a topic is considered at all, so a false positive reopens the leak it exists to close: as substrings, "spectra" matches "spectral normalization" and "spectral clustering" — ordinary ML vocabulary — and "clip" matches "eclipse". There is a test for exactly this.
- Gate terms never enter the relevance denominator, so the lists can be generous (37 terms) without costing score.
- Applied to the three praxis topics and to `sim-to-real-transfer-astronomy`, whose vocabulary ("domain adaptation", "transfer learning", "distribution shift") is generic ML and would otherwise pull in robotics. `transient-photometric-classification` is deliberately left ungated — its vocabulary is already domain-locked, so a gate would be a no-op.
- Exposed on `GET`/`POST`/`PUT /topics` and round-tripped through the YAML loader.

#### Keyword pruning (PR #78)

- Removed author surnames, one venue name, and short acronyms from three topics: `33 → 27`, `28 → 24`, `33 → 29`. Also dropped `AstroM³` as a duplicate spelling of `AstroM3`.
- Two distinct kinds of pure denominator cost. Author names and `MICCAI` effectively never appear in an abstract. Short acronyms are worse than useless — keyword matching is substring-based, so `ECE` matched "pi**ece**", `ViT` matched "gra**vit**y", `CLIP` matched "e**clip**se", `LoRA` matched "f**lora**". In an astronomy corpus those fired constantly while contributing nothing.
- Generic-but-core terms ("conditional diffusion", "contrastive learning") were **kept**. The gate is what makes them safe, which was the point of adding it.

### Fixed

#### Only one topic per track was being searched (PR #77)

- `_aggregate_keywords()` walked topics depth-first, exhausting the highest-weight topic's list before touching the next. Any topic holding more keywords than the whole budget consumed it alone. With a five-keyword budget and `generative-cross-modal-imputation` (33 keywords) sorted first, the entire praxis track searched only cross-modal-imputation vocabulary; `missing-modality-learning` contributed nothing at equal weight, so the learnable-token half of the work was invisible to discovery. Same shape on the astro side.
- v2.8's per-track grouping fixed the scope-level version of this and relocated the track-level one rather than removing it.
- Aggregation is now round-robin — one value from each topic in turn, tiers ordered by weight so the highest-weight topic still picks first. Category aggregation had the identical shape at `limit=3` and got the same fix.
- Measured on the live topic set, praxis went from one of three topics supplying terms to three of three, and astro from one of two to two of two.

#### astronomy-foundations was winning the astro track (PR #77)

- Marked prerequisite-only, mirroring `ml-foundations`. A live run had it taking **both** astro slots with general astronomy — ionized nebulae around symbiotic stars, hydrocarbon detection on Titan — rather than transient work, because it matches broadly and carried a 365-day recency window. It was single-handedly widening the track's window from the 90 days `transient-photometric-classification` asks for; removing it from the quota group drops the track to 180 days.

### Operations

- **One new migration, additive with an idempotent guard**: `0017_topic_require_any`. Parent `0016_topic_track`, single head. Verified upgrade → downgrade → upgrade against a copy of the dev database.
- **`scripts/assign_topic_tracks.py --apply` is a required post-deploy step**, and carries more than it did in v2.8: the domain gates and pruned keyword lists as well as the track assignments. `config/topics/private/` is gitignored, so the database is the only place that configuration can live. Without this step the `require_any` column ships empty and the release changes nothing.
- **Zero new Python or npm dependencies. Zero new environment variables.**
- This range includes a back-merge of `main` into `develop`, which returned the v2.8 changelog and release notes to the integration branch. No product change.

### Decisions

- **The gate matches whole words while keywords match substrings.** They answer different questions. A keyword false positive costs a little score; a gate false positive admits an entire off-domain literature. Substring matching would have let "spectral normalization" satisfy an astronomy gate.
- **Medical missing-modality vocabulary was kept, not deleted.** That literature is where learnable modality tokens come from. The gate scopes it to papers that also mention an astronomical context, rather than forcing a choice between losing the method literature and importing all of medical imaging.
- **`min_relevance` was left unchanged.** Pruning raises scores for genuine matches and the gate removes a class of false positive; both push the same direction, so moving the threshold at the same time would risk emptying a track and make it impossible to attribute which change did what. Revisit after a few live runs.
- **`transient-photometric-classification` is ungated.** Its vocabulary is already domain-locked; a gate would add maintenance for no filtering.

### Followups

- **An untracked remainder still receives its own paper quota.** With `scope_mode='all'`, untracked topics are grouped into a single bucket and `select_daily_papers()` treats it like any track. Round-robin made its character worse, not better: it previously searched five terms from one foundations topic, and now samples five unrelated fields (atmospheric physics, cell biology, classical mechanics, climate, financial economics). Scoping to the tracked topics (`scope_mode='multi'`) works around it. The code should probably not treat leftovers as a peer of tracks that were deliberately defined.
- **Within a track, the loosest topic still sets the threshold.** Astro sits at `min_relevance` 0.17, inherited from the demoted `sim-to-real-transfer-astronomy`, rather than the 0.18 the primary topic asks for. Narrowest-wins versus weight-weighted remains an open preference call.
- **`scripts/check_track_balance.py`'s "BEFORE" comparison is now inaccurate.** It calls the live `_aggregate_keywords`, which this release changed, so the BEFORE branch no longer reproduces the old depth-first behaviour — it reports round-robin over the whole scope instead. The label overstates the historical baseline (it now prints "5 of 22" where the true pre-v2.9 figure was "1 of 22"). Freezing that branch as an inline loop would fix it.
- **The 0.6 keyword / 0.4 category weighting** means a paper can accumulate meaningful relevance from arXiv category overlap alone, which is part of why thresholds behave less intuitively than the keyword lists suggest. Not obviously wrong; not yet examined.
- **No frontend surface for tracks or gates.** Both fields are on the API responses; there are no badges and no track-sectioned daily view.

## [v2.8] — 2026-09-04

Paper discovery stops being monopolized by a single topic, and a v2.7 auth regression that broke the first request after every login gets fixed. **Research tracks ship** (PR #73) — topics now declare a `track`, and discovery runs an independent pass per track, so each gets its own keyword budget instead of competing for one global top-five list; on the live topic set that global list was supplied entirely by one topic, leaving six of seven topics contributing nothing to discovery at all. **A session-lookup regression from v2.7 is fixed** (PR #74) — the `last_seen_at` throttle added in `li6` committed while the `User` it was about to return was still in the identity map, stranding it and 500ing the first authenticated request after every login. **The Claude review workflow is repaired** (PR #75) — it had been passing v0.x input names to `claude-code-action@v1`, which dropped them, found no prompt, and cancelled the job on every PR. **One new migration, zero new dependencies, zero new environment variables.** Full release notes in [docs/releases/v2.8.md](docs/releases/v2.8.md).

### Added

#### Research tracks for paper discovery (PR #73)

- New `Topic.track` (nullable, indexed) and `Topic.prerequisite_only` (boolean) columns, migration `0016_topic_track`. Both round-trip through the topic YAML loader and are exposed on `GET`/`POST`/`PUT /topics`, so the in-app editor can't silently drop them.
- `discover_papers_by_track()` groups quota-eligible topics by track and runs a full discovery pass per group via `_discover_for_topics()`. Each track gets its own `_aggregate_keywords(limit=5)` and `_aggregate_categories(limit=3)` budget rather than sharing one across the whole scope. Papers are scored only against their own track's topics, so a strong match in one track is no longer marked down for failing to match another track's keywords.
- `select_daily_papers(quota_per_track=N)` returns `{track: [papers]}`, filtering each track against **its own** `min_relevance` and recency window instead of the most permissive value anywhere in scope. A track with nothing above threshold returns fewer papers rather than borrowing another track's slots. `select_daily_paper()` is retained as a wrapper for existing callers, and now picks the best candidate across tracks rather than the global top-ranked paper.
- Cross-track duplicates are resolved to whichever track scored the paper higher, so one paper can't fill two quotas.
- `prerequisite_only` marks foundations topics that should shape review and quiz generation but never consume a daily paper slot. `ml-foundations` is set this way; its keywords no longer become search terms.
- `scripts/assign_topic_tracks.py` sets `track` / `weight` / `prerequisite_only` on existing topic rows (dry-run by default, `--apply` to write, safe to re-run). It exists because `config/topics/private/` is gitignored and never reaches a deployment, making track assignment a data step rather than a config change.
- `scripts/check_track_balance.py` prints the per-track keyword and category budgets alongside the old global aggregation — including how many topics contributed any search term at all — and with `--live` runs a real discovery pass and prints what each track selected.
- `README.md` gains a "Research tracks" section covering both fields, the truncation problem that motivated them, the untracked fallback, and both scripts.

### Fixed

#### First authenticated request after login returned 500 (PR #74)

- `lookup_session_user()` (`backend/services/auth_sessions.py`) called `session.commit()` for the throttled `last_seen_at` write while the `User` loaded a few lines earlier was still in the identity map. `expire_on_commit` defaults to `True` on our sessionmaker, so that commit expired the `User`; the following `session.expunge()` then detached an already-expired instance, which can never reload itself. The caller hit `DetachedInstanceError` on its first attribute read — `user.status` inside `_resolve_session_user_id()`.
- Impact was wider than the test failures suggested. The throttle fires whenever `last_seen_at IS NULL` — true for every brand-new session — and then once per `SESSION_LAST_SEEN_THROTTLE` (15 minutes). An authenticated request 500s immediately after login, works for fifteen minutes, 500s again, and repeats. Because it surfaces as a 500 on the auth dependency rather than a 401, the frontend reports it as "backend unreachable" rather than as an auth problem, which is how it survived the v2.7 release.
- Fixed by expunging the user before the session-row write, so the commit has nothing of ours left in the identity map to expire.
- All 20 `expunge()` call sites were audited. Nine have a `commit()` in the preceding lines; eight of those already use `commit() -> refresh(obj) -> expunge(obj)` correctly (`services/scopes.py`, `invite_codes.py`, `topic_subscriptions.py`). This was the only omission — a single gap introduced when the `last_seen_at` throttle was layered onto correct code, not a pattern applied wrongly across the codebase.
- Restores the full suite to green: **321 passed, 1 skipped, 0 failed**, from 26 failed / 300 passed. That also cleared three intermittent `test_user_isolation` push-subscription failures that had been failing on `develop` before this work started and turned out to be downstream of the same bug.

#### Claude PR review workflow cancelled itself on every run (PR #75)

- `.github/workflows/claude-review.yml` still passed `direct_prompt` and `timeout_minutes`, neither of which `claude-code-action@v1` accepts. Unknown inputs are warned about and dropped rather than failing the step, so the prompt arrived empty; the action logged `Context prompt: NO PROMPT`, resolved `Trigger result: false`, skipped its remaining steps and cancelled the job. GitHub renders that cancellation identically to a genuine test failure, so every PR carried a red check that had never examined the diff.
- `direct_prompt` renamed to `prompt` (documented as a drop-in replacement in the v1 migration guide); `timeout_minutes` moved from the action input to the job-level `timeout-minutes` key. The prompt body is unchanged. The repo and PR number are now prepended to the prompt, per the v1 automatic-review example, with the PR number falling back to `github.event.issue.number` so the `@claude` comment trigger keeps working.

### Operations

- **One new migration, additive with idempotent guards**: `0016_topic_track` (`track` and `prerequisite_only` on `topics`). Parent `0015_session_last_seen`, single head. Verified upgrade → downgrade → upgrade against a copy of the dev database.
- **`scripts/assign_topic_tracks.py --apply` is a required post-deploy step.** Without it every topic keeps `track=NULL`, discovery falls back to its pre-v2.8 single-pool behaviour, and this release changes nothing in production. The fallback is deliberate — it is what keeps scopes that never declared tracks working — which also means the missing step fails silently rather than loudly.
- **Zero new Python or npm dependencies. Zero new environment variables.**
- `README.md` updated with the "Research tracks" section, per the README rule in `CLAUDE.md`.

### Decisions

- **One scope with a balanced per-track quota, rather than two scopes to switch between.** Switching scopes would have needed no new code, but it means seeing one track per day unless you remember to switch. The quota keeps both tracks in a single daily view.
- **An under-filled track returns fewer papers rather than borrowing the other track's slots.** Silently backfilling would hide exactly the failure this release exists to fix; an under-filled day is honest signal that a track's keywords or threshold need attention.
- **Foundations topics are marked `prerequisite_only` rather than deactivated.** They still inform review and quiz generation, they just stop competing for daily paper slots against the topics a track exists to follow.
- **The two straddling topics were demoted to weight 0.8, not deactivated.** They're still genuinely relevant; they just shouldn't outrank the topics the tracks are built around.
- **The #74 fix expunges before the commit instead of adopting the codebase's `commit -> refresh -> expunge` pattern.** Both work. Here the user is not the object being written, so `refresh()` would re-read a row we already hold purely to undo an expiry we caused, and it would add an `ObjectDeletedError` path for a concurrently deleted user on a function that already has a clean "user is None" branch. The reasoning is recorded in a comment at the call site so the next reader doesn't "restore consistency" and reintroduce the bug.
- **The #74 fix rides this release rather than being cut as a standalone hotfix to `main`.** It is a live production bug, but the beta population is small enough that a release of one commit isn't warranted.

### Followups

- **Verified live, and it surfaced two things this release does not fix.** `scripts/check_track_balance.py --live` was run against the production topic set after merge to `develop`. Both tracks returned papers (astro 2, praxis 2), confirming per-track discovery works end to end. It also showed:
  - **An untracked remainder becomes a third quota bucket.** With `scope_mode='all'` (the default) all 22 active topics are in scope — the two tracks plus 15 untracked starter and user-created topics — and `select_daily_papers()` gives every bucket its own quota, the untracked one included. The two highest-scoring papers of the run were untracked (climate science 0.335, statistical mechanics 0.315), outranking everything in either real track. Grouping was designed so a scope with *no* tracks behaves exactly as before; it should also have handled a scope with *some* tracks by not treating the leftovers as a track of their own. Workaround today is to scope to the tracked topics (`scope_mode='multi'`).
  - **Inside the astro track, the foundations topic dominates.** Both astro selections matched `astronomy-foundations` rather than `transient-photometric-classification` — general astronomy (symbiotic stars, Titan spectroscopy) rather than transient work — and it is also what widens the track's window to 365 days. A concrete instance of the within-track issue below. Making `astronomy-foundations` prerequisite-only, mirroring `ml-foundations`, is the obvious next move; it was left open in this release because it would leave `transient-photometric-classification` as the only topic feeding the astro quota, and whether that track still clears its threshold is untested.
  - Praxis selections cleared their threshold only narrowly (0.196 and 0.176 against a 0.17 floor) and were off-domain — medical-imaging inpainting and neural compilation rather than astronomy cross-modal work. Keyword tuning, not a code issue, but worth a pass before trusting a day's output.
  - Several Semantic Scholar queries returned HTTP 429 and were skipped; arXiv carried the run. Existing behaviour, not introduced here, but it means a live run's coverage varies between invocations.
- **Within a track, the loosest topic still sets the parameters.** `_scope_min_relevance` takes the lowest value in a track and `_scope_max_recency` the widest. On the current astro scope that means `astronomy-foundations` (365 days) widens the whole track's window despite `transient-photometric-classification` asking for 90, and the demoted `sim-to-real-transfer-astronomy` (0.17) sets the threshold rather than the primary topic's 0.18. Narrowest-wins versus weight-weighted is a preference call, deliberately left open.
- **No frontend surface for tracks yet.** `track` is on the API response and on `Paper.to_dict()`, but there are no track badges and no track-sectioned daily view.
- **`on.pull_request.branches` in the review workflow lists `feature/**`, `bugfix/*` and `release/*`**, but that filter matches the PR's base branch, not its head. Since everything targets `develop` or `main`, those three entries match nothing. Harmless, but it implies head-branch filtering that isn't happening.
- **Whether `astronomy-foundations` should also be `prerequisite_only` is unresolved.** It's the astro-side mirror of `ml-foundations`, but demoting it would leave `transient-photometric-classification` as the only topic feeding the astro quota.
- **Backend `pytest` still isn't run in CI** — carried forward from earlier releases. The suite is now green, which makes wiring it up cheaper than it has been.

## [v2.7] — 2026-07-10

Push notifications finally get a way to turn them on, plus a device-management page for logins. **The push-subscribe UI ships** (`pn1`) — `useWebPush.ts` was fully built back in Phase 3 but never called from any page; it now lives as a "This device" card on `/settings/notifications`, with explicit messaging for iOS Safari's install-first requirement. **A CSRF gap in the push endpoints is fixed** — found while manually testing the subscribe flow above, since the hook's raw `fetch()` calls skipped the app's automatic CSRF header. **Session (device) management ships** (`li6`) — a new `/settings/account/sessions` page lists active logins with device/browser, IP, and last-active time, with per-device revoke and a "log out everywhere else" option, built on top of session infrastructure (`li2`) that already existed but had no UI. **One new migration, zero new dependencies, zero new environment variables.** Full release notes in [docs/releases/v2.7.md](docs/releases/v2.7.md).

### Added

#### Push notification subscribe UI (PR #70, pn1)

- Wired `frontend/hooks/useWebPush.ts` into a new "This device" card on `frontend/app/settings/notifications/page.tsx` — permission request, subscribe/unsubscribe, and a "Send test push" button, plus messaging for unsupported browsers and for iOS Safari specifically when the app hasn't been added to the home screen yet (push only reaches installed PWAs on iOS 16.4+).
- The hook itself was fully implemented since an earlier Phase 3 round (permission → `pushManager.subscribe()` → `POST /push/subscribe`, graceful 503 handling, `sendTest()`) but never called from any page or component — confirmed via a repo-wide grep, matching `FUTURE_FEATURES.md`'s own `pn1` entry, which had it flagged as scaffolded-but-dead-code. This PR is purely the missing UI; no backend changes.

#### Session (device) management (PR #70, li6)

- New `/settings/account/sessions` page lists active login sessions — device/browser parsed from the stored user-agent, raw IP, and relative last-active time — with a per-session revoke button and a "log out everywhere else" action (self-reauth pattern: your current session stays alive, same as the existing password-change flow).
- Backend: `list_sessions_for_user()` / `revoke_session_by_id()` (`backend/services/auth_sessions.py`), three new endpoints on `auth_router` (`GET /auth/sessions`, `POST /auth/sessions/{id}/revoke`, `POST /auth/sessions/log-out-everywhere`), and a `last_seen_at` column on `Session` (migration `0015_session_last_seen`) written on a 15-minute throttle so the "active N min ago" display doesn't cost a DB write on every request.
- The `sessions` table already had `user_agent`/`ip`/`created_at`/`expires_at`/`revoked_at` and a full revoke service layer built for the password-change flow — its own docstring called the session-list UI out as "a follow-up phase." This exposes that existing plumbing as real UI for the first time. Deliberately kept separate from the push-subscription "This device" card above — different table, different identity shape (`PushSubscription.user_id` is a string handle, `Session.user_id` is an integer FK), different lifecycle.
- New nav entry ("Sessions") added to `Sidebar.tsx` / `MobileTabBar.tsx`'s Account group, alongside Profile/Password/Username.

### Fixed

- **Push subscribe/unsubscribe/test 403'd with "CSRF token missing or invalid"** (PR #70) — `useWebPush.ts` made raw `fetch()` calls that bypassed `lib/api.ts`'s automatic CSRF header injection (`fetchAPI()` normally attaches `X-CSRF-Token` on every mutating request; the hook's hand-rolled fetches didn't). Invisible until the subscribe UI above actually shipped and got exercised for the first time — this is exactly the kind of gap that stays hidden in dead code. Fixed by exporting a `csrfHeader()` helper from `lib/api.ts` and applying it to all three of the hook's POST calls. `uploadPdfToPaper` / `uploadStandalonePdf` in `lib/api.ts` have the same raw-`fetch()`-bypasses-CSRF pattern; not touched in this release, flagged as a followup.

### Operations

- **One new migration, purely additive with an idempotent guard**: `0015_session_last_seen` (new `last_seen_at` column on `sessions`).
- **Zero new Python or npm dependencies.**
- **Zero new environment variables.** `VAPID_SUBJECT` (documented since an earlier release) was already set correctly in production; only a local `.env` needed a one-line uncomment to unblock local testing, not tracked in git since `.env` is gitignored.
- `docs/PWA.md` and `README.md` updated — both previously described enabling push via `/settings/scope`, a flow that never actually existed since the subscribe button was dead code until this release; now describe the real `/settings/notifications` "This device" card.
- `FUTURE_FEATURES.md`: `pn1` marked fully shipped (previously flagged scaffolded-not-wired-up); new `li6` entry added under Phase 1 for session management; Phase 1/Phase 3 status-overview lines updated to match.

### Decisions

- **Session management is its own page, not merged into the push-subscription "This device" card.** They're deliberately separate concepts — a device can be logged in without push enabled, or push-subscribed on a tab that's since logged out — and the two underlying tables don't even share an identity representation (string handle vs. integer FK), which would make a unified view awkward beyond just the UX question.
- **`last_seen_at` written on a 15-minute throttle, not every request.** Keeps the "active N min ago" display reasonably fresh without turning every authenticated request into a `sessions` table UPDATE.
- **No concurrent-session limit added.** Consistent with existing (unlimited) behavior; not scoped for this release.

### Followups

- **No automated test coverage added** for `revoke_session_by_id` / `list_sessions_for_user` — same gap noted in prior releases (no frontend test framework; backend `pytest` suite not wired into CI).
- **`uploadPdfToPaper` / `uploadStandalonePdf` likely have the same CSRF gap** fixed for the push endpoints in this release (raw `fetch()`, no `X-CSRF-Token`) — not confirmed against a live 403, not fixed here.
- **VAPID key rotation story still undocumented** — carried forward from Phase 3's open questions in `FUTURE_FEATURES.md`.
- **Production `next build` not verified in the environment this was built in** — a sandboxed build hit permission conflicts against a live `.next/` directory; confirm manually before/after deploy.

## [v2.6] — 2026-07-05

Self-serve password reset + admin ops tooling + a from-scratch theming system release. **Password reset goes fully self-serve** — a real SMTP-delivered reset link (`li3b`) replaces the old ask-an-admin workaround, with a console-logged fallback so local dev needs zero setup. **The admin console gains its final three tabs**, closing out Phase 2 — Topics (import/export YAML, orphaned-topic filtering), Cache (per-user targeted cache-bust), and Stats (usage overview plus a full quiz-performance breakdown with leaderboards) (`ad4`/`ad5`). **Display settings go from zero to ten themes** — editorial/dark/observatory shipped as the foundation alongside font-size options and an app-wide legacy-color sweep, then Soft Morning, Noir, Brutalist, Muted, High Contrast, Pride, and Random landed on top, three of them (Soft Morning, Noir, High Contrast) with their own multi-hue accent picker and Random with a fully deterministic weekly rotation that needs no cron job at all. **Long-form generated content gets its own reading-font picker** (Merriweather / Source Sans 3), independent of theme (`fd2`). **Two new migrations, zero new dependencies, one new optional env-var family (`SMTP_*`, safe to leave unset in local dev).** Full release notes in [docs/releases/v2.6.md](docs/releases/v2.6.md).

### Added

#### Self-serve password reset via SMTP email (PR #59, li3b)

- **`POST /auth/forgot-password`** (`backend/api/auth.py`) looks up the account by email via `backend/services/password_reset.py` and, if it's active, mints a single-use `password_reset_tokens` row (30 min TTL, migration `0013_password_reset`) and emails a reset link. Always returns the same generic response regardless of whether the email matched an account, so the endpoint can't be used to enumerate registered emails.
- **`POST /auth/reset-password`** consumes the token and sets the new password.
- **`backend/services/email.py`** — a stdlib `smtplib` wrapper, no third-party email SDK dependency. Configured via new `SMTP_*` settings in `backend/config.py` / `.env.example`; when `SMTP_HOST` is unset, the reset link is logged to the console instead of sent, so the whole flow is testable with zero email setup.
- Both new endpoints are IP-rate-limited via the existing `backend/middleware/rate_limit.py`.
- New pages: `frontend/app/forgot-password`, `frontend/app/reset-password`, matching the existing `AuthShell` styling; the login page now links to forgot-password.
- An earlier iteration of this feature used an email+username knowledge check instead of real email (no proof of inbox ownership) — replaced once SMTP was wired up, since proving inbox ownership is the correctly-scoped identity check for a password reset.

#### Admin Topics, Cache, and Stats tabs (PR #60, ad4 + ad5)

- **Topics tab** — wires the already-existing `POST /topics/import-yaml`, `POST /topics/export-yaml`, and `GET /topics?include_orphaned=` endpoints into an actual UI: import/export buttons with a result summary, an orphaned-only filter, and active/orphaned/system-vs-user-owned badges per topic.
- **Cache tab** — `DELETE /admin/cache/{user_id}` (`backend/api/admin.py`) clears every `daily_content_cache` row for one target user, looked up via the existing account list. Every bust is audit-logged (`EventType.CACHE_BUST`, `backend/services/audit_log.py`). Scoped to a single targeted user deliberately — see Followups.
- **Stats tab** — `GET /admin/stats/overview` (user counts by status, content volume, 30-day signup trend) and `GET /admin/stats/quiz-performance` (overall/median/average score, score distribution, per-topic and per-difficulty accuracy breakdowns sorted worst-first, a 30-day score trend, and two leaderboards — most active, and highest accuracy gated behind a minimum-questions floor so one lucky quiz can't top the board). Derived entirely from the existing `ArchivedQuiz.questions` JSON — no new instrumentation needed. No charting library exists in this project, so the bars/sparklines/leaderboards are hand-rolled CSS rather than a new frontend dependency.

#### Theme foundation: plumbing, three themes, font sizes, app-wide sweep (PR #61, fd3 foundation)

- New `display_settings JSON` column on `user_settings` (migration `0014_display_settings`), backend registry (`backend/services/display.py`) and API (`backend/api/display.py`) for theme + font-size preferences.
- Tailwind's color palette refactored to CSS custom properties as RGB-triplet strings, wrapped as `rgb(var(--x) / <alpha-value>)` in `tailwind.config.js` — the only pattern that keeps Tailwind's `/NN` opacity modifiers (`bg-rust/5`, etc.) working with CSS-variable-driven theme colors; a bare `var(--x)` hex string builds fine but silently drops any opacity-modified utility.
- Three themes shipped: **editorial** (the existing look, now themeable), **dark** (same layout/fonts, recolored), **observatory** (near-black instrument panel, Bodoni Moda display face).
- Four font sizes (small/medium/large/extra large) via `[data-font-size="..."]` scaling the `<html>` root font-size — every rem-based Tailwind utility scales automatically.
- New `/settings/display` page (theme cards + font-size picker, live preview on click, single Save) and a new "Appearance" nav group in `Sidebar.tsx`/`MobileTabBar.tsx`.
- App-wide legacy-color sweep: ~1,000 hardcoded Tailwind color-class occurrences converted to theme tokens across 29 files, plus background/text classes added to 57 native form controls that had none, so dark/observatory render correctly everywhere instead of just on the pages built after the sweep. `color-scheme` set in `globals.css` so native OS-drawn form chrome (select dropdowns, date pickers) also follows the active theme.

#### Soft Morning, Noir, and Brutalist themes (PR #62, fd3)

- **Soft Morning** — blush pastel, rounded shapes, Fraunces + Nunito.
- **Noir** — cold true grayscale (deliberately no warm undertone, unlike Observatory's amber glow), Bebas Neue + Work Sans.
- **Brutalist** — stark black/white, thick hard-edge borders, offset shadows, Archivo Black + Space Mono. `--rule` is reused as solid near-black so every existing `border-rule` utility renders bold for free, plus a `[data-theme="brutalist"] * { border-radius: 0; box-shadow: none; }` reset — no component edits needed for the hard-edge look.

#### Colorful accents for Soft Morning and Noir (PR #63, fd3)

- New `THEME_ACCENTS` registry (`backend/services/display.py`) and `[data-theme="..."][data-accent="..."]` CSS override blocks — only `--gold`/`--gold-dark` change between accents.
- **Soft Morning**: orange (baseline), rose, sage, sky, lavender — pastel weight.
- **Noir**: cobalt (baseline), crimson, emerald, violet, amber — fully saturated, since a pastel tint would disappear against Noir's near-black surfaces.
- `/settings/display` grew a conditional Accent swatch section that only renders for themes with a non-empty accent list.

#### Muted, High Contrast, Pride themes, and Random (PR #64, fd3)

- **Muted** — desaturated stone/greige, single dusty-clay accent, Cormorant Garamond display face (body stays Inter deliberately, so the "quiet" identity comes from restraint, not a font swap).
- **High Contrast** — pure black/white verified against WCAG (body text 21:1, secondary text 9.6:1, non-text borders 4.1:1, all clear AAA; danger red ~6.9:1 clears AA). Atkinson Hyperlegible — a typeface built for low-vision readability — replaces both the display and body face. Its own 4-option accent picker: cyan (baseline, 13.7:1) and orange (8.9:1) clear AAA; magenta (6.5:1) and violet (6.2:1) clear AA.
- **Pride** — clean warm-neutral base, Fredoka + Figtree, single solid pink accent wired into the app's existing `--gold`/`--gold-dark` slot. The progressive pride flag's full palette (black/brown/light-blue/pink/white plus the classic six) shows up separately as a decorative 4px gradient ribbon pinned to the top of the viewport (`[data-theme="pride"] .app-shell::before`), not a full recolor.
- **Random** — a meta-theme with no palette of its own. `resolve_random()` hashes `user_id` + a theme/accent purpose tag + the current ISO week (Monday-anchored, UTC) via `crc32` into a pick from every other registered theme (and that theme's accent pool, if it has one). No cron or stored rotation state needed — the ISO week number is the clock, so the weekly reset happens for free at the Sunday/Monday boundary, and each user's pick is independent. `/settings/display` shows a "This week: `<theme>` · `<accent>`" caption when Random is selected.

#### Reading-font picker for generated content (PR #65, fd2)

- New theme-independent `reading_font` setting — `theme` (no-op default), `merriweather`, `source_sans` — scoped to long-form generated content only (`.prose-scholar`, i.e. topic reviews and paper summaries), so it can't clash with any theme's own bespoke typography.
- New `GET /display/reading-fonts` endpoint; `/settings/display` grew a Reading font pill picker that renders unconditionally, unlike the theme-gated Accent section.

### Fixed

- **`.prose-scholar` (generated topic reviews / paper summaries) was still on hardcoded `slate`/`blue` Tailwind classes** (PR #65) — a gap the fd3 app-wide sweep missed since this block lives in `globals.css` rather than a page file. Converted to theme tokens while this exact block was already being touched for the reading-font work; code blocks use `ink-2`/`paper-2` (inverted, neutral) rather than the `gold-dark` swap used for `slate-900` elsewhere, since a code block should read as a neutral dark surface on every theme, not an accent-colored one.
- **`/settings/display`'s live click-preview stopped working** (PR #64 follow-up) — `applyDisplaySettings` needed to paint `resolved_theme`/`resolved_accent` instead of `theme`/`accent` directly (so Random always resolves to a real palette), but the page's `pickTheme`/`pickAccent` handlers only updated `theme`/`accent` locally. Clicking a theme card did nothing visually until Save's server round-trip returned a fresh `resolved_theme` — exactly matching what got reported (switches on save, not on click). Fixed by mirroring the click into `resolved_theme`/`resolved_accent` too, except when picking "random" itself, where there's no client-side hash and the resolved fields still only catch up after Save.
- **`docker-compose.yml`'s `FRONTEND_URL` pointed at the compose-network-only `http://frontend:3000`** (PR #59) — broke the clickability of local-dev password-reset links (CORS still worked either way via a hardcoded `localhost` fallback, so this went unnoticed until a real link needed to be clicked). Changed to `http://localhost:3000`, the browser-reachable address.

### Operations

- **Two new migrations, both purely additive with idempotent guards**: `0013_password_reset` (new `password_reset_tokens` table) and `0014_display_settings` (new `display_settings JSON` column on `user_settings`, mirroring `notification_settings` from `0004`).
- **Zero new Python or npm dependencies.** Email sending uses stdlib `smtplib`; no charting library was added for the Stats tab (hand-rolled CSS instead).
- **New optional env-var family**: `SMTP_HOST` / `SMTP_PORT` / `SMTP_USE_TLS` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` (`.env.example`). All optional — leaving `SMTP_HOST` blank falls back to console-logging the reset link, so this is safe to skip in dev/CI, but **production needs it configured for password reset to actually send email.**
- **`docs/DEPLOY.md`** updated: `SMTP_*` added to the "same in both environments" env-var group for the Railway dev+prod split (one mailbox/relay shared across envs is fine — reset emails aren't secret), and a note that `FRONTEND_URL` is also the base URL password-reset links point at, so a wrong value there sends users to the wrong environment's reset page.
- **New Phase 6 in `FUTURE_FEATURES.md`** capturing the admin cache-bust follow-ups deliberately left out of this release (see Followups).

### Decisions

- **No cron or scheduler for Random.** The ISO week number itself is the clock — a `crc32` hash of `user_id` + purpose + ISO year/week gives a deterministic, different-per-user pick that resets for free at the week boundary. Verified via a standalone harness: same result on repeat calls within a week, flips exactly at the Sunday 23:59 → Monday 00:01 UTC boundary, and distributes roughly evenly across all 9 real themes over 2000 synthetic users.
- **Reading-font picker scoped to generated content only, not a global override.** Every theme now has its own bespoke display/body typography (Bebas Neue for Noir, Archivo Black for Brutalist, Cormorant Garamond for Muted, etc.); a global font override would have undone all of that. Confirmed with the reviewer before implementing.
- **Brutalist and Muted ship single-accent only; Soft Morning, Noir, and High Contrast get the multi-hue picker.** A deliberate split, not every theme needing the same treatment.
- **Cache-bust scoped to single-user targeting for this release.** Multi-select and a global "clear for everyone" option are real, useful follow-ups, but coarse/irreversible enough (in effect, even though it's just cache) to deserve their own explicit design pass rather than being rushed in — captured as Phase 6 instead.
- **`smtplib` over a third-party email SDK.** Matches li3b's original scoping and keeps `requirements.txt` unchanged.

### Followups

- **Phase 6 · Admin Cache Tooling** — multi-user select for cache bust (`ct1`) and a global "clear for everyone" option (`ct2`), both not started. See `FUTURE_FEATURES.md` for gating conditions.
- **Random's rotation cadence is fixed at weekly.** A user-configurable cadence (daily/weekly/monthly, or a custom schedule) instead of the fixed weekly reset is noted in `FUTURE_FEATURES.md` under fd3; not started.
- **fd0, fd1, and fd4** (the remaining Phase 5 frontend-enhancement items) are still not started.
- **Should admin actions push-notify the affected user** (e.g. "an admin disabled your account")? Still an open question from Phase 2 — no such notification kind exists yet.

## [v2.5.1] — 2026-07-03

Small polish release. **Admin-generated invite codes gain an optional custom-text option** — left blank, still a random `secrets.token_urlsafe` code as before; typed in, validated (3–32 chars, letters/digits/-/_) and used as-is. **The dashboard's stats bar is redesigned** to match the editorial theme (Fraunces numerals, roman-numeral eyebrows, hairline rule borders) instead of standing out as a leftover blue/indigo gradient, and **a flexbox bug clipping the sidebar's "in scope" card down to a sliver is fixed**. Also corrects stale deploy-config comments in `frontend/railway.toml`. **Zero new migrations, zero new dependencies, zero new environment variables.** Full release notes in [docs/releases/v2.5.1.md](docs/releases/v2.5.1.md).

### Added

#### Custom invite codes (PR #56)

- New optional "Custom code" text input next to the Create button on `/settings/admin`'s Invite codes tab. Left blank, unchanged random-code behavior; typed in, validated and used as-is.
- `generate_invite_code()` (`backend/services/invite_codes.py`) gains an optional `custom_code` param — validates charset/length (3–32 chars: letters, digits, `-`, `_`) and checks for a collision, no retry-on-collision (a silently different code than what the admin typed would be worse than an error). New `InviteCodeInvalid` / `InviteCodeTaken` exceptions map to `400`/`409` in `backend/api/admin_invites.py`.
- `CreateInviteBody` (both the Pydantic model and the frontend `CreateInviteBody` type in `frontend/lib/api.ts`) gains an optional `code` field.

### Changed

- **Dashboard stats bar redesigned** (`frontend/app/page.tsx`, PR #57) — replaced the `bg-gradient-to-r from-blue-600 to-indigo-600` band with four bordered `bg-paper-2` "numbered cards" (Streak / Read / Kept / Accuracy), each with an italic roman-numeral eyebrow and a large Fraunces numeral; the streak card is the visual hero with a rust-to-gold top accent. `FireIcon` gained an optional `className` prop so it could be recolored/resized for the smaller card icon. Three directions were explored as local (gitignored) HTML mockups before picking this one.
- **`frontend/railway.toml` deploy comments corrected** (PR #55) — updated to describe the actual v2.4+ same-origin `/api/*` proxy shape (`BACKEND_INTERNAL_URL` required, `NEXT_PUBLIC_API_URL` an optional escape hatch requiring `COOKIE_DOMAIN` if used) instead of the stale pre-v2.4 `NEXT_PUBLIC_API_URL`-required guidance. No behavior change.

### Fixed

- **Sidebar "in scope" card could clip down to a ~26px sliver** (`frontend/components/ActiveScopeChip.tsx`, PR #55, PR #56) — the card is a flex item inside the flex-column sidebar and also has `overflow-hidden` (to clip its diagonal-hatch background to the rounded corners); setting `overflow` to anything but `visible` on a flex item removes its automatic minimum-size floor, so it was the one item that could shrink below its own content whenever the rail's total content exceeded the viewport, clipping the scope name/topic count/"Change scope" link down to just the "IN SCOPE" label. Fixed by adding `shrink-0` to all three render states. Made independently in both PR #55 and PR #56; the resulting merge conflict (same class, different attribute order) was trivially resolved.

### Operations

- **Zero new migrations, zero new dependencies (Python or npm), zero new environment variables.** Invite codes reuse the existing `InviteCode` model/column; the stats bar and sidebar fix are presentational only.

### Decisions

- **No retry-on-collision for custom invite codes.** Unlike the random-code generator's 5-attempt uniqueness retry, a requested custom code that's already taken returns a `409` rather than silently substituting a different code — the admin explicitly asked for that text.
- **Observatory-styled stats bar mockup kept as a future theme candidate, not discarded or shipped as default.** See Followups.

### Followups

- **Observatory theme as a user-selectable preference** — the dark amber "night observatory" stats-bar mockup explored alongside the shipped design is a candidate for a proper alternate visual theme (a persisted `users.theme`-style preference plus a toggle in `/settings/account`), not just a one-off palette swap. Marked with a `TODO(design)` comment in `frontend/app/page.tsx`; not built yet.
- **No live "code already taken" check before submit** on the custom invite code field — the `409` only surfaces after clicking Create. Fine given how rarely admins would hit a real collision; a live-availability check is a small nice-to-have if usage grows.

## [v2.5] — 2026-07-02

Settings IA rebuild + AI-assisted scope creation release. **Settings gets a real hierarchy** — Scope, Notifications, Account, Tutorials, and Admin become sibling sections, with Sidebar/MobileTabBar as the single source of cross-section navigation, replacing the scattered per-page "Account →"-style link clusters. **Scope creation gains an AI-drafting path** — a new "Generate scope" wizard (reachable any time from Settings > Scope, not just first-run onboarding) turns a title + description into a draft set of keywords / arXiv categories / key concepts, editable as bubbles rather than raw text, before creating a topic wrapped in a single-topic scope. Also folds in the prior notifications-page redesign (plain-English schedule summaries replacing the raw cron string), an iOS Safari bottom-nav anchoring fix (#50), and a license change (#53: MIT → PolyForm Noncommercial 1.0.0). **Zero new migrations, zero new dependencies, zero new environment variables.** Full release notes in [docs/releases/v2.5.md](docs/releases/v2.5.md).

### Added

#### Settings information architecture restructure (PR #51)

- **New routes**: `/settings/scope/library`, `/settings/scope/browse`, `/settings/scope/requests` (moved off the old `/scopes/browse` and `/scopes/requests`, plus the combined scope page split into a dedicated library view); `/settings/account/profile`, `/settings/account/password`, `/settings/account/username` (split out of one combined account page); `/settings/tutorials` (new — consolidates the tour-replay picker that used to be independently implemented three times, in `Sidebar.tsx`, `MobileTabBar.tsx`, and the account page's `TourReplayCard`, each maintaining its own copy of the tour list).
- **Old bare routes redirect**: `/settings/scope` → `/settings/scope/library`, `/settings/account` → `/settings/account/profile`, via Next.js Server Component `redirect()` so old bookmarks/links still land somewhere sensible.
- **Sidebar + MobileTabBar restructured** to mirror the new IA exactly: Scope, Notifications (promoted out of Account into its own group), Account (split into Profile/Password/Username), Tutorials (single link, replacing the inline tour picker), and Admin (a real nav entry for the first time, gated on `user.role === 'admin'` — `Sidebar()` didn't previously call `useAuth()` at all).
- Per-page "related link" clusters (Browse public / Access requests / Account / Admin links scattered across scope pages) removed now that nav lists every destination — Sidebar/MobileTabBar are the single source of truth for cross-section navigation.

#### Generate-scope wizard (PR #52)

- **New `/settings/scope/generate` page**: title + description in, calls the existing `generateTopicDraft()` client (hits `POST /onboarding/generate-topic`) to draft keywords/arXiv categories/key concepts, then on approval creates a `Topic` via `POST /topics` and wraps it in a `scope_mode='silo'` `Scope` via `POST /scopes`. The new scope lands in the library but does **not** auto-activate.
- **`ChipListEditor`** (`frontend/components/ChipListEditor.tsx`, new) — reusable bubble-style editor for a `string[]` field, replacing the raw-textarea convention (`TopicForm.tsx`) for this specific review-and-approve interaction. Click a chip to select it, then Edit/Delete via a small toolbar; a separate "+ Add" chip reveals a text input with autocomplete — recommendations only ever surface in the add flow, never while editing an existing chip.
- **Suggestion pools** for the chip autocomplete are drawn from the user's visible topic catalog (real keywords/concepts already in use, via the existing `listTopics()`) rather than fabricated, plus a static real arXiv category taxonomy (`frontend/lib/arxivCategories.ts`) merged in for the categories field specifically.
- "Generate scope" surfaced next to "New scope" in the library page and in Sidebar/MobileTabBar's Scope group.
- Backend test coverage added: `backend/tests/test_topics.py` (new — `POST /topics` had zero prior coverage despite real ownership/visibility branching logic) and a new `test_silo_with_exactly_one_topic_succeeds` in `test_scopes.py` (every existing silo-mode test previously only asserted rejection, not the actual success path this feature depends on entirely).

#### Human-readable notification schedules (PR #50)

- Each notification card now leads with a plain-English schedule sentence ("Every day at 9:00 AM") built from the underlying cron expression, with the raw cron tucked behind a small info affordance instead of shown as the primary UI. Falls back to a raw, editable cron field if a power user has hand-edited the JSON to something the friendly picker can't represent, so it's never silently overwritten.
- New `to12h`/`to24h`/`fmt12` helpers power a 12-hour time stepper in place of the old raw `HH:MM` text input.

### Changed

- `NotificationDispatchResult.result` (`frontend/lib/api.ts`) gained `skipped`/`subscriptions` fields — `send_push_to_user()` can nest a `skipped` reason inside `result` (e.g. VAPID unconfigured, no subscriptions) distinct from the top-level `skipped` (the builder itself had nothing due today); the notifications UI previously only checked the top-level field, so a real skip reason could go unreported.
- `ScopeTour`'s `fire_on_path` and `ActiveScopeChip`'s "Change scope" link updated to the new `/settings/scope/library` path (`useDriverTour` gates on an exact pathname match, not a prefix, so this needed an explicit update rather than relying on prefix-matching).
- `ScopePickerGuard`/`OnboardingGuard`'s `SKIP_PREFIXES` needed no changes — both already matched `/settings/scope` as a prefix, which still covers every route moved under it.
- **License switched from MIT to PolyForm Noncommercial 1.0.0** (PR #53) — `LICENSE` replaced in full, `README.md`'s License section updated to match and link to the PolyForm project page. Commercial use now requires permission from the copyright holder. No code changes.

### Fixed

- **iOS Safari bottom-nav "floating" during scroll** (PR #50) — `MobileTabBar`'s fixed nav lacked its own GPU compositor layer, so iOS Safari rendered it lagging behind page content during momentum scroll (worse while the dynamic toolbar collapses). Fixed with `transform: translateZ(0)` + `WebkitBackfaceVisibility: hidden` to promote it to its own layer.

### Operations

- **Zero new migrations, zero new dependencies (Python or npm), zero new environment variables.** Nav/routing and UI-layer changes only.

### Decisions

- **Generate-scope wizard reuses the onboarding generation endpoint directly** rather than adding a new one — `generate_topic_draft`/`POST /onboarding/generate-topic` were never actually onboarding-gated server-side (only requires a signed-up user), so exposing the existing client (`generateTopicDraft()`) from a new entry point was the whole change.
- **Suggestions grounded in real catalog data, not fabricated** — keyword/concept autocomplete pulls from the user's actual visible topics rather than inventing a vocabulary; only the arXiv categories field gets a static taxonomy merged in, since that one has a genuine fixed, stable set of valid codes.
- **`/scopes/picker` kept as a separate route**, not merged into `/settings/scope/new` — it serves a distinct first-run flow gated by `ScopePickerGuard`, not general scope creation.
- **New scope from the wizard does not auto-activate** — added to the library only; matches forking or picking a starter scope, keeps the "what's currently active" mental model simple.
- **Frontend test infrastructure bootstrap deferred to its own PR** rather than introduced as a side effect of this release — scoped out in `FUTURE_FEATURES.md` under "Engineering quality" with the specific tests (ChipListEditor interactions, the wizard's two-phase create-flow partial-failure branch) already identified.

### Followups

- **Frontend has no test framework at all** (no Jest/Vitest/Testing Library). See `FUTURE_FEATURES.md` → "Frontend test infrastructure" for the scoped-out plan.
- **`VAPID_SUBJECT` is commented out in `.env`**, discovered incidentally while running the backend suite for this release (causes 3 pre-existing, unrelated push-subscription test failures — `test_user_isolation.py::TestPushSubscriptionIsolation`). Not touched by this release; worth a one-line uncomment whenever push notifications need to actually work.
- **Backend `pytest` suite still isn't run in CI** — `.github/workflows/` only runs Alembic migration checks. Noted in `FUTURE_FEATURES.md` as worth bundling with the frontend CI question if/when that lands.
- **The three-option "Account →" nav-button redesign** (bylines / chips / command-rail mockups) explored earlier in this cycle was superseded by the IA restructure — nav now lists every destination directly, so the per-page link-cluster redesign is no longer needed. Mockups not implemented; can be discarded.
- **License is now noncommercial-only.** Anyone relying on the prior MIT terms for commercial use should be aware of the change; no other action needed.

## [v2.4] — 2026-06-29

Editorial UI + production stability release. **The sticky top nav is replaced with a 280px persistent editorial left sidebar** (cream paper + Fraunces serif + warm gold accent) reorganized into hierarchical groups (Read / Scope / Account / Help) with a pinned active-scope chip at the top of the rail. Mobile keeps the bottom tab bar but reskinned to match, with the More sheet regrouped to mirror the sidebar IA. New "Replay tutorials" picker on both surfaces re-fires a specific product tour via a new optional `?tour_id=` parameter on `PUT /auth/tour-reset`. Folded in: hotfix #46 (same-origin `/api/*` proxy, already shipped to main, unblocks prod login post-Cloudflare-Access removal) and bugfix #47 (iOS Dynamic Island safe-area, post-onboarding redirect loop, uvicorn keep-alive vs Next.js proxy `ECONNRESET`, mobile More sheet polish). **Zero new migrations, zero new dependencies, one new Railway env var (`BACKEND_INTERNAL_URL`), one removed (`NEXT_PUBLIC_API_URL`), one opt-in env var added then immediately rendered moot by same-origin (`COOKIE_DOMAIN`).** Nav-only structural change — every existing page, route, and guard still works. Full release notes in [docs/releases/v2.4.md](docs/releases/v2.4.md).

### Added

#### Editorial sidebar overhaul (PR #48)

- **Tailwind palette + typography** — extended with `paper / ink / muted / rule / gold / gold-dark / rust / moss` tokens; legacy `scholar / surface` tokens preserved so existing pages keep rendering. `font-serif` → Fraunces, `font-mono` → IBM Plex Mono. `globals.css` imports the three Google Fonts (Fraunces + IBM Plex Mono + Inter), defines CSS custom properties for the full palette, sets warm-paper body background with two radial glows + SVG-noise `body::before` overlay, repoints scrollbar thumbs to the warm tones.
- **`frontend/components/Sidebar.tsx`** (new, 450 lines) — 280px persistent left rail on `md+`: wordmark, pinned `ActiveScopeChip`, four named groups (Read / Scope / Account / Help) with hierarchical sub-items, `UserChip` footer with small logout popover. Hides on `/login`, `/signup`, `/account/*`.
- **`frontend/components/ActiveScopeChip.tsx`** (new, 124 lines) — calls `getActiveScope()` on mount; three states: loading skeleton (height-stable), empty prompt linking to `/scopes/picker`, ready chip showing scope name + topic count + `edited Xh ago` via inline `formatRelative` helper.
- **`frontend/app/layout.tsx`** rewritten as a two-column flex shell; `themeColor` → `#F2EBDD` so iOS chrome blends into the paper; main column padding-top `calc(env(safe-area-inset-top) + 2rem)` preserves the v2.3 Dynamic Island clearance.
- **`frontend/components/MobileTabBar.tsx`** reskinned to cream/gold palette (gold underline for active tab, paper-2 sheet background, Fraunces section labels); More sheet regrouped into Scope / Account / Help to mirror the sidebar IA. Bottom tabs unchanged at Today / Papers / Topics / Quizzes / More.

#### Tour replay picker + per-tour reset (PR #48)

- **`PUT /auth/tour-reset`** now accepts an optional `?tour_id=<id>` query param — with it, only that key's seen-version zeroes (rest of `tour_state` untouched); without it, existing full-reset behavior. Validated against `KNOWN_TOUR_IDS`; unknown ids return 400 with the same error shape as `mark_tour_completed`.
- **`frontend/lib/api.ts`** exposes `resetTour(tour_id?: string)` so callers can request either flavor.
- **Help group on both surfaces** gains a "Replay tutorials" entry: tapping it swaps the same section in-place into a picker with three choices (Dashboard / Scope library / Topics); selecting one calls `resetTour(id)`, refreshes `/auth/me`, then `router.push`-es to the tour's `fire_on_path`. Pulsing gold play icon + IBM Plex Mono "loading" tag for the in-flight state; back chevron returns to the default Help list.
- Two new tests in `backend/tests/test_tour_versioning.py`: per-tour reset clears only the target key; unknown id returns 400 without mutating state.

### Changed

- **Sticky top nav → persistent left sidebar on `md+`.** Mobile bottom tab bar retained. Hides on auth/account surfaces so `<AuthBoundary>` still owns the viewport there.
- **`OnboardingGuard.SKIP_PREFIXES`** extended with `/scopes` and `/settings/scope` so the guard can't yank users off scope-setup surfaces mid-flow if onboarded state goes briefly stale (PR #47).
- **`skipOnboarding()` and `completeOnboarding()`** now emit the `AUTH_CHANGED_EVENT` window event after success — `useAuth` is a per-component hook with no React context, so cross-instance sync only happens via this event. `login()` / `logout()` already emitted it; the onboarding mutations didn't, which caused the layout-mounted `OnboardingGuard` to loop on stale `user.onboarded === false` (PR #47).
- **Mobile More sheet** gains a Notifications row (matching the new desktop nav entry) and tightens Settings active-state highlighting so it no longer falsely activates for non-scope `/settings/*` paths (PR #47; superseded by IA regroup in PR #48 but documented for the audit trail).
- **`backend/main.py` middleware stack reordered.** CORS is now the OUTERMOST layer (last `add_middleware` call wins under Starlette's LIFO wrapping); request flow is `CORS → RateLimit → CSRF → handler`, response flow is `handler → CSRF → RateLimit → CORS` so CORS headers attach to every response — including early 403s from the inner CSRF / rate-limit middlewares (otherwise an inner early-return surfaces in the browser as a misleading "CORS error"). `backend/middleware/csrf.py` updated in lockstep so CSRF cookies respect `COOKIE_DOMAIN` when set. Commit `e2abd80`, reviewed alongside hotfix #46.
- **`.gitignore`** now matches `*mockups/` to keep design exploration artifacts (this cycle: `nav-mockups/` with three nav-layout HTML prototypes) out of git. Mirrors the v2.1 pattern for `daily scholar/`.

### Fixed

- **iOS Dynamic Island clipping the sticky nav** — added `paddingTop: env(safe-area-inset-top)` to the sticky `<nav>` in the root layout. `viewportFit: "cover"` was already set so the page extended under the Dynamic Island; without the inset, nav contents sat behind the island on iPhone 14 Pro and later (PR #47). The PR #48 sidebar rewrite preserves the clearance via `calc(env(safe-area-inset-top) + 2rem)` on the main column.
- **Post-onboarding redirect loop** — `OnboardingGuard` kept a stale `user.onboarded === false` after `completeOnboarding()` / `skipOnboarding()` returned, bounced users back to `/onboarding`, looped until something else triggered a refetch. Root cause: missing `AUTH_CHANGED_EVENT` emission on the onboarding mutations (PR #47).
- **`ECONNRESET` / `socket hang up` spam on `/auth/me`, `/user/active-scope`, `/scopes/mine`, `/daily`** — Next.js 16's `rewrites()` proxy (undici-backed) pools outgoing connections with ~75s idle; uvicorn's default `--timeout-keep-alive` is 5s, so the proxy reused already-closed sockets. Bumped uvicorn to `--timeout-keep-alive 75` in both the production Dockerfile CMD and `start.sh` (PR #47).
- **Production login broken after Cloudflare Access removal** — `ds_csrf` cookie set by `api.daily-scholar.com` wasn't readable by JS at `scholar.daily-scholar.com`, so the double-submit-cookie CSRF pattern couldn't work cross-subdomain. CF Access had been masking this by authenticating at the edge. Fixed by collapsing to same-origin via Next.js `rewrites()` proxying `/api/:path*` → `${BACKEND_INTERNAL_URL}/:path*`; cookies now scoped to `scholar.daily-scholar.com`, JS can read them, CSRF + CORS class of bugs goes away (hotfix #46).

### Operations

- **Required Railway env-var change BEFORE the v2.4 image will build correctly:**
  - **ADD** `BACKEND_INTERNAL_URL=http://backend.railway.internal:8000` on the **frontend** service. Next.js bakes `rewrites()` destinations into the route manifest at build time, so changing it requires a rebuild (same trade-off as the old `NEXT_PUBLIC_API_URL`).
  - **REMOVE** (or leave empty) `NEXT_PUBLIC_API_URL` on the **frontend** service. Leaving it set would override the `/api` default and bypass the proxy.
  - Confirm the backend service's private hostname under Settings → Private Networking is `backend.railway.internal`. Adjust if you renamed the service.
- **New backend env var `COOKIE_DOMAIN`** (opt-in). Read by `_cookie_domain()` in both `backend/api/auth.py` and `backend/middleware/csrf.py`; unset → origin-scoped cookies (the desired behavior under same-origin). Added during commit `e2abd80` as part of the cross-subdomain debugging; left in place as a no-op safety valve. **Production should NOT set it.**
- **Production Dockerfile rebuild required** — the uvicorn `--timeout-keep-alive 75` flag is baked into the CMD; no live-reload path will pick it up.
- **Backend service's `api.daily-scholar.com` custom domain** can stay one release as a safety net; delete after v2.4 is verified.
- **Cookies are now first-party.** `ds_session` + `ds_csrf` set by `scholar.daily-scholar.com` (not the deleted `api.*` host). Old cookies expire naturally; first login on the new build issues fresh ones.
- **No new migrations, no new pip deps, no new npm deps.**
- **No new GitHub Actions secrets.** Railway deploy matrix unchanged from v2.2.

### Decisions

- **Same-origin proxy over cross-subdomain CORS + cookie-domain juggling.** Standard pattern; matches what most modern stacks assume; eliminates an entire class of future cross-origin surprises. The cost is the build-time Next.js bake of `rewrites()` destinations, which is the same cost the old `NEXT_PUBLIC_API_URL` already had.
- **Per-tour reset (`?tour_id=`) as a query param on the existing endpoint**, not a separate route. Same JSON-payload shape, same `KNOWN_TOUR_IDS` validation, same 400 error envelope — lets the inverse of `markTourCompleted` slot into the existing tour-state machinery without a second client helper or a second handler.
- **Persistent left sidebar over collapsible drawer on desktop.** The active scope is consulted on basically every page; making it a one-click destination from anywhere costs 280px of horizontal real estate but pays it back in friction reduction. Mobile keeps the bottom tab bar (one-tap reach) — the More sheet is the only place the IA hierarchy expands.
- **Cream paper + Fraunces serif over neutral grey + sans.** "Daily reading" product should look like a journal, not a SaaS dashboard. Editorial palette also makes the active-scope chip's warm gold accent legible without competing for attention.

### Followups

- **PWA install flow** on the new layout — no functional change but worth a smoke check before announcing v2.4.
- **iOS Safari + Dynamic Island on physical hardware** — still pending from v2.1; v2.4 changes the nav structure so verification should re-run.
- **`UserMenu.tsx`** is unused by the new layout; safe to delete in a cleanup PR if it stays orphaned.
- **`TOUR_CHOICES` array duplication** between `Sidebar.tsx` and `MobileTabBar.tsx` (with a comment pointing at backend `KNOWN_TOUR_IDS` as the source of truth) — fine for three entries; revisit if a fourth tour is added (e.g., a DiscoverTour for `/topics/discover`, filed as v2.2 followup).
- **CORS allowlist + `FRONTEND_URL`** in `backend/main.py` become harmless dead code under same-origin; remove in v2.5 alongside the OAuth work.
- **OAuth login** — the `feature/oauth-login` branch is still in flight; deferred past v2.4 deliberately so the editorial UI ships independently.

## [v2.3] — 2026-06-27

Scope library release. **Scope becomes a first-class, shareable, forkable entity** instead of a single hidden per-user setting. Five system-owned starter scopes (ML, Physics, Biology & Life Sciences, Economics & Finance, Climate & Earth Sciences) drive a new onboarding picker for fresh users; existing users get migrated transparently. Public scopes are searchable and forkable; private scopes are shareable via a request/approval workflow mirroring v2.2's invite-code pattern. **One migration (`0012_scopes`), three new tables, one new column, twelve new starter-topic YAMLs, zero new dependencies, zero env-var changes.** Solo mode (`__local__`) and the legacy `/user/scope` shape preserved end-to-end. Full release notes in [docs/releases/v2.3.md](docs/releases/v2.3.md).

### Added

- **Scope entity** — `scopes` table (id, name, description, owner_user_id, visibility, mode, topic_ids, forked_from_scope_id, timestamps). `UserSettings.active_scope_id` points at the row currently driving discovery / review / quizzes. Legacy `scope_mode` / `scope_topic_ids` columns kept as a one-release back-compat cache, refreshed by the service when the user switches active scope.
- **Scope library API** — `GET /scopes/mine` (owned + granted with relation tag), `GET /scopes/search?q=` (public substring search), `GET/POST/PUT/DELETE /scopes[/{id}]` (CRUD), `PUT /scopes/{id}/visibility`, `POST /scopes/{id}/fork`.
- **Active-scope API** — `GET /user/active-scope` (full row or `null`), `PUT /user/active-scope` (body `{"scope_id": id | null}`).
- **Access-request lifecycle** — `POST /scopes/{id}/access-requests` (recipient asks), `GET /scopes/access-requests/incoming|outgoing` (status-filterable), `POST /scopes/access-requests/{id}/decide` (owner approves/denies). Approval inserts a `ScopeAccessGrant`; one pending per (scope, requester) enforced in the service layer.
- **Five starter scopes + twelve foundation topics** under `config/topics/starter/`. New `backend/services/starter_scopes.py` seeds them at boot (idempotent, refreshes topic_ids if the catalog grows); also runnable via `scripts/seed_starter_scopes.py`.
- **Frontend** — `/settings/scope` rewritten as the library view, new `/settings/scope/[id]` per-scope editor, new `/scopes/browse` for public discovery + fork (with Use Directly action + Request-access-by-id form), new `/scopes/requests` for the two-section access-request inbox, new `/scopes/picker` for first-run users. `<ScopePickerGuard />` mounted in layout. `ScopeTour` bumped to v2.
- **Migration script** — `scripts/migrate_to_scope_library.py` materializes per-user legacy `scope_mode` / `scope_topic_ids` into a private `"My scope"` row and sets `active_scope_id`. Dry-run by default; `--apply` to commit. Idempotent.

### Changed

- **`backend/services/scopes.delete_scope`** does explicit cleanup (clears active pointers, breaks fork lineage, drops grants + requests) rather than relying on FK CASCADE / SET NULL, matching `topic_subscriptions`'s "don't depend on `PRAGMA foreign_keys`" convention.
- **Migration `0012_scopes`** adds the three tables + the `active_scope_id` column. `backend/main.py` `lifespan` calls `seed_starter_scopes()` right after `bootstrap_topics_from_yaml()` so a fresh boot always has the starter content.

### Preserved

- `GET /user/scope` and `PUT /user/scope` (the legacy shape paper discovery + quiz code reads). Reads project from the active scope; writes update the active scope's cache in place.
- Solo mode (`__local__`) — treated as admin for view + edit permission checks. Starter scopes are visible to it; the migration script skips it (no `users` row).

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
