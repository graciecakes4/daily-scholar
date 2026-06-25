# Install as a PWA

Daily Scholar ships as a Progressive Web App: install it on your phone, tablet, or desktop and it behaves like a native app — its own window, a home-screen icon, offline access to recently visited pages.

## Install paths by platform

| Platform | How to install | Notes |
|---|---|---|
| **iOS Safari** | Share button → **Add to Home Screen** | Required step for iOS; the in-app banner explains it the first time. iOS won't fire a native install prompt. |
| **macOS Safari** | File → **Add to Dock** | Safari 17+. |
| **macOS / Windows / Linux Chrome / Edge** | Address-bar install icon, or in-app **Install** button | The Install banner appears automatically on capable browsers. |
| **Android Chrome** | In-app **Install** button (or browser menu → Install app) | Native install prompt fires after the first visit. |

## What works offline

Once installed, the service worker caches:

- The **app shell** (HTML/CSS/JS) — opens instantly even offline.
- **Recently fetched API responses** (papers, topics, archive, daily content) — 24h NetworkFirst cache, so you see the last fresh data when offline.
- **PDFs** you've already viewed — CacheFirst, kept for 90 days.

Actions you take while offline (saving a paper, marking a topic completed, scope updates) are queued in a **background sync queue** and replay automatically when you're back online.

The dev server (`npm run dev`) skips service-worker registration to keep hot-reload sane. To test the PWA end-to-end, build and serve production:

```bash
cd frontend
npm run build         # builds with webpack (see below)
npm start
# open http://localhost:3000 in Chrome with DevTools → Application → Service Workers
```

> **Why the build uses webpack instead of Turbopack:** Next.js 16 defaults to Turbopack, but `@serwist/next` v9 injects its service-worker build via a webpack plugin and isn't Turbopack-compatible yet (see [serwist/serwist#54](https://github.com/serwist/serwist/issues/54)). The `build` script already passes `--webpack`, so this is invisible to you in normal use — but if you ever want to migrate to Turbopack for the production build, you'll need to swap `@serwist/next` for `@serwist/turbopack` or move to configurator mode. Dev (`npm run dev`) stays on Turbopack with the service worker disabled, so HMR remains fast.

## Push notifications

Daily Scholar can push a notification when a new daily paper is generated. Setup is one-time:

```bash
# 1. Generate a VAPID keypair (do this ONCE; reuse forever)
python scripts/generate_vapid_keys.py

# 2. Paste the three printed lines (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT)
#    into your .env

# 3. Restart the backend so it picks up the new env vars
make start
```

> **Important:** regenerating the VAPID keypair invalidates every existing browser subscription — clients silently stop receiving pushes until they re-subscribe via the toggle. Treat the keys like an API secret.

### Enabling notifications in the app

Visit `/settings/scope` and click **Enable notifications** under the Notifications section. The browser will:

1. Ask permission to send notifications.
2. Subscribe to push events with your server's VAPID public key.
3. POST the subscription to the backend (`/push/subscribe`).

After that, every time `/daily` generates a fresh paper (either nightly or via the **New paper** button), all your subscribed devices get a push: *"Today's paper is ready — «title»"*. Tapping it opens (or focuses) the dashboard.

There's a **Send test** button in the same settings section to fire a sanity-check push without waiting for a real paper.

### Per-platform support

| Platform | Works? | Caveat |
|---|---|---|
| Android Chrome | ✓ | Native install + push, no extra setup |
| Desktop Chrome / Edge / Firefox | ✓ | Pushes arrive whether the browser is open or not |
| macOS Safari 16+ | ✓ | Add the site to the Dock first |
| **iOS Safari 16.4+** | ✓ *with caveat* | Must **Add to Home Screen first** — iOS only delivers pushes to installed PWAs. The settings page shows an amber hint if it detects you haven't yet. |

### Adding more trigger points (future)

The push fanout helper is `backend/services/push_sender.py`. Anywhere in the backend can call:

```python
from .services.push_sender import send_push_to_user
send_push_to_user(user_id, {"title": "...", "body": "...", "url": "/topics/foo"})
```

Examples of where you might wire it next: a daily "topics due for review" digest from APScheduler, a notification when an LLM-generated quiz is ready, or a streak-reminder.

## Swapping the app icon

Icons live in `frontend/public/icons/`. The placeholder set (book-on-slate) was generated; replace any of `icon-{192,256,384,512}.png` and the matching `*-maskable.png` to rebrand. Required sizes are referenced in `frontend/public/manifest.json` and `frontend/app/layout.tsx`.

For a one-shot regenerate from a single 512×512 source image:

```bash
python3 -c "
from PIL import Image
src = Image.open('frontend/public/icons/source.png')
for s in (192, 256, 384, 512):
    src.resize((s, s), Image.LANCZOS).save(f'frontend/public/icons/icon-{s}.png', 'PNG', optimize=True)
"
```
