'use client';

/**
 * Guided product tour for first-time-onboarded users on the dashboard.
 *
 * Uses `driver.js` (5KB, framework-agnostic, React-19-compatible) for
 * the spotlight + popover. We originally tried `react-joyride` 2.x but
 * it imports React-18-only APIs (`unmountComponentAtNode`,
 * `unstable_renderSubtreeIntoContainer`) that React 19 dropped, so the
 * webpack build failed. driver.js is imperative — no React component
 * tree — so we drive it from a useEffect and clean up on unmount.
 *
 * Versioning + server-side tracking:
 *   - `TOUR_VERSION` is the current schema version of the tour. Bump
 *     it when you add/remove a step or materially rewrite copy.
 *   - The server stores `users.tour_version_seen` (returned on
 *     `/auth/me`). Tour fires when `tour_version_seen < TOUR_VERSION`.
 *   - On completion (finished OR closed early) we POST the new version
 *     and call `refresh()` so the in-memory auth state matches the
 *     server. Cross-device sync; no localStorage involved.
 *
 * Each step targets an element with a `data-tour="..."` attribute on
 * the dashboard or nav. Stable data-attrs (not class names or ids)
 * survive UI restyling.
 *
 * Replay via the "Show me around again" button on `/settings/account`
 * (which calls `resetTour()` to zero the server value, then routes to /).
 */

import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { markTourCompleted } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

/**
 * Current version of the dashboard tour.
 *
 * BUMP this constant when you change the STEPS array in a way that
 * users should see again — added/removed steps, materially rewritten
 * copy, new target element. Existing users whose `tour_version_seen`
 * is below the new value will see the tour again on next dashboard
 * visit; users at-or-above will not.
 *
 * Don't bump for cosmetic-only tweaks (style, typo fixes) — those
 * aren't worth re-interrupting users who already finished the tour.
 */
export const TOUR_VERSION = 1;

// Routes where the tour should NEVER fire — we don't want it overlapping
// auth flows or the onboarding wizard. The /-only check below already
// filters most of these out; this is belt-and-braces.
const SKIP_PATHS = new Set(['/login', '/signup', '/onboarding']);
const SKIP_PREFIXES = ['/account/'];

const STEPS = [
  {
    element: '[data-tour="paper"]',
    popover: {
      title: "Today's paper",
      description:
        "Each day we surface one paper from your topics. Read the summary, " +
        "save it to your archive, or mark it done — we remember what you've read.",
      side: 'bottom',
      align: 'start',
    },
  },
  {
    element: '[data-tour="review"]',
    popover: {
      title: 'Topic review',
      description:
        "A quick refresher on one of your topics each day. The topic itself " +
        "(keywords, key concepts) is what you manage from Settings → Topics.",
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '[data-tour="quiz"]',
    popover: {
      title: 'Quiz',
      description:
        "Test what you've learned. Questions are generated from your topics' " +
        "key concepts and adapt to what you've already mastered.",
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '[data-tour="settings"]',
    popover: {
      title: 'Settings',
      description:
        "Everything else lives here — manage your topics, schedule study reminders, " +
        "change your password or handle, and (if you're an admin) manage other users.",
      side: 'bottom',
      align: 'end',
    },
  },
];

function _shouldSkipPath(pathname: string | null): boolean {
  if (!pathname) return true;
  if (SKIP_PATHS.has(pathname)) return true;
  return SKIP_PREFIXES.some(p => pathname.startsWith(p));
}

export default function DashboardTour() {
  const { user, loading, refresh } = useAuth();
  const pathname = usePathname();

  useEffect(() => {
    // All gates must pass before we fire:
    //   - auth loaded + user logged in + onboarded
    //   - on the dashboard (where the tour targets live)
    //   - not on an auth/onboarding/account route
    //   - user hasn't already seen the current TOUR_VERSION
    if (loading) return;
    if (!user || !user.onboarded) return;
    if (!pathname || pathname !== '/') return;
    if (_shouldSkipPath(pathname)) return;
    if ((user.tour_version_seen ?? 0) >= TOUR_VERSION) return;

    let driverInstance: any = null;
    let cancelled = false;

    (async () => {
      try {
        // dynamic imports so driver.js doesn't run in SSR, and the CSS
        // only loads when the tour actually fires
        const mod = await import('driver.js');
        // @ts-expect-error CSS imports have no TS type but Next handles them
        await import('driver.js/dist/driver.css');
        if (cancelled) return;

        driverInstance = mod.driver({
          showProgress: true,
          allowClose: true,
          popoverClass: 'ds-tour-popover',
          stagePadding: 8,
          stageRadius: 8,
          // Both finishing the last step AND closing early fire onDestroyed.
          // POST the version we showed, then refresh /auth/me so the
          // gating check picks up the updated tour_version_seen on the
          // next render and doesn't try to refire.
          onDestroyed: async () => {
            try {
              await markTourCompleted(TOUR_VERSION);
              await refresh();
            } catch (e) {
              // network hiccup — the tour is already off-screen and
              // we'd rather not block the user. They'll see it again
              // on next visit; not the end of the world.
              console.warn('DashboardTour: failed to mark tour completed', e);
            }
          },
          steps: STEPS as any,
        });
        driverInstance.drive();
      } catch (e) {
        console.warn('DashboardTour: failed to load tour engine', e);
      }
    })();

    return () => {
      cancelled = true;
      if (driverInstance) {
        try { driverInstance.destroy(); } catch { /* ok */ }
      }
    };
    // intentionally NOT depending on `refresh` (stable from useAuth);
    // re-running the effect on refresh-identity-change would re-fire
    // the tour each time we refetch /auth/me
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user?.tour_version_seen, user?.onboarded, user?.user_id, pathname]);

  return null;
}
