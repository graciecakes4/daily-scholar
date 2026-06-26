'use client';

/**
 * Shared driver.js plumbing for the three product tours
 * (DashboardTour, ScopeTour, TopicsTour). Each tour component imports
 * this hook, supplies its config, and stays ~40 lines instead of ~150.
 *
 * Server-side versioned state: gates on `user.tour_state[tour_id]`
 * vs the supplied current `version`. On completion (or close-early),
 * POSTs the version + refreshes /auth/me so the gate stops re-firing.
 *
 * Self-gates on:
 *   - auth loaded + user logged in + onboarded
 *   - `pathname === fire_on_path` (each tour only runs on its own page)
 *   - user.tour_state[tour_id] < version
 */

import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { markTourCompleted } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

export interface DriverStep {
  element: string;        // CSS selector — typically '[data-tour="…"]'
  popover: {
    title: string;
    description: string;
    side?: 'top' | 'right' | 'bottom' | 'left';
    align?: 'start' | 'center' | 'end';
  };
}

export interface UseDriverTourOptions {
  /** Stable id passed to markTourCompleted; must match KNOWN_TOUR_IDS on the backend. */
  tour_id: string;
  /** Current tour version. Bump when STEPS materially change. */
  version: number;
  /** Only fire on this exact pathname. */
  fire_on_path: string;
  /** Tour steps in display order. */
  steps: DriverStep[];
}

export function useDriverTour({
  tour_id,
  version,
  fire_on_path,
  steps,
}: UseDriverTourOptions): void {
  const { user, loading, refresh } = useAuth();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user || !user.onboarded) return;
    if (!pathname || pathname !== fire_on_path) return;
    const seen = user.tour_state?.[tour_id] ?? 0;
    if (seen >= version) return;

    let driverInstance: any = null;
    let cancelled = false;

    (async () => {
      try {
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
          // Both finish and close-early fire onDestroyed. POST the
          // version then refresh /auth/me so the next render's gate
          // sees the updated tour_state and doesn't try to refire.
          onDestroyed: async () => {
            try {
              await markTourCompleted(tour_id, version);
              await refresh();
            } catch (e) {
              console.warn(`tour ${tour_id}: failed to mark completed`, e);
            }
          },
          steps: steps as any,
        });
        driverInstance.drive();
      } catch (e) {
        console.warn(`tour ${tour_id}: failed to load driver.js`, e);
      }
    })();

    return () => {
      cancelled = true;
      if (driverInstance) {
        try { driverInstance.destroy(); } catch { /* ok */ }
      }
    };
    // intentionally exclude `refresh` (stable from useAuth); re-running on
    // refresh-identity-change would re-fire the tour each time we refetch
    // /auth/me. user.tour_state for THIS tour is what should re-evaluate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user?.user_id, user?.onboarded, user?.tour_state?.[tour_id], pathname]);
}
