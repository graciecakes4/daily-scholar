'use client';

/**
 * Tutorial for /settings/scope — the scope library.
 *
 * 2 steps (deliberately small):
 *   1. Active scope banner — what "active" means + how it drives the app
 *   2. Library list + new scope button — owned + shared scopes, plus
 *      how to add more
 *
 * Per-scope editing (mode + topic picker + save) lives on
 * /settings/scope/[id]; that page has its own data-tour anchors and may
 * get a separate tour later.
 *
 * BUMP TOUR_VERSION when STEPS materially changes. Frontend gates
 * on `user.tour_state.scope < TOUR_VERSION`; bumping re-triggers
 * the tour for everyone whose stored value is lower. v1 targeted the
 * old single-scope page (data-tour="scope-mode" / "scope-save"); v2
 * targets the library shell.
 */

import { useDriverTour } from '@/hooks/useDriverTour';

export const TOUR_ID = 'scope';
export const TOUR_VERSION = 2;

const STEPS = [
  {
    element: '[data-tour="scope-active"]',
    popover: {
      title: 'Your active scope',
      description:
        "Exactly one scope is active at a time. The active scope decides " +
        "which topics drive paper discovery, topic review, and quizzes. " +
        "Click the name to edit it, or hit Set Active on any other scope to switch.",
      side: 'bottom' as const,
      align: 'start' as const,
    },
  },
  {
    element: '[data-tour="scope-library"]',
    popover: {
      title: 'Your library',
      description:
        "Scopes you own and ones that have been shared with you. " +
        "Hit “New scope” to start one from scratch, or use Browse public " +
        "to fork a starter scope from the catalog.",
      side: 'top' as const,
      align: 'end' as const,
    },
  },
];

export default function ScopeTour() {
  useDriverTour({
    tour_id: TOUR_ID,
    version: TOUR_VERSION,
    fire_on_path: '/settings/scope/library',
    steps: STEPS,
  });
  return null;
}
