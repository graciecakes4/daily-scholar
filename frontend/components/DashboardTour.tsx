'use client';

/**
 * Guided product tour for first-time-onboarded users on the dashboard.
 *
 * Implementation details (server-side versioning, driver.js, gating
 * logic) live in `useDriverTour`. This file just declares the steps,
 * the tour_id, and the current TOUR_VERSION.
 *
 * BUMP TOUR_VERSION when STEPS materially changes (added/removed step,
 * meaningfully rewritten copy). Existing users whose
 * `tour_state.dashboard < TOUR_VERSION` see the tour again on next
 * dashboard visit. Don't bump for cosmetic-only tweaks.
 */

import { useDriverTour } from '@/hooks/useDriverTour';

export const TOUR_ID = 'dashboard';
export const TOUR_VERSION = 1;

const STEPS = [
  {
    element: '[data-tour="paper"]',
    popover: {
      title: "Today's paper",
      description:
        "Each day we surface one paper from your topics. Read the summary, " +
        "save it to your archive, or mark it done — we remember what you've read.",
      side: 'bottom' as const,
      align: 'start' as const,
    },
  },
  {
    element: '[data-tour="review"]',
    popover: {
      title: 'Topic review',
      description:
        "A quick refresher on one of your topics each day. The topic itself " +
        "(keywords, key concepts) is what you manage from Settings → Topics.",
      side: 'bottom' as const,
      align: 'center' as const,
    },
  },
  {
    element: '[data-tour="quiz"]',
    popover: {
      title: 'Quiz',
      description:
        "Test what you've learned. Questions are generated from your topics' " +
        "key concepts and adapt to what you've already mastered.",
      side: 'bottom' as const,
      align: 'center' as const,
    },
  },
  {
    element: '[data-tour="settings"]',
    popover: {
      title: 'Settings',
      description:
        "Everything else lives here — manage your topics, schedule study reminders, " +
        "change your password or handle, and (if you're an admin) manage other users.",
      side: 'bottom' as const,
      align: 'end' as const,
    },
  },
];

export default function DashboardTour() {
  useDriverTour({
    tour_id: TOUR_ID,
    version: TOUR_VERSION,
    fire_on_path: '/',
    steps: STEPS,
  });
  return null;
}
