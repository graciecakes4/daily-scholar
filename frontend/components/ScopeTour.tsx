'use client';

/**
 * Tutorial for /settings/scope — the silo/multi/all topic-scope selector.
 *
 * 2 steps (deliberately small — scope is one decision, not a workflow):
 *   1. Mode selector — what the three modes do
 *   2. Save button — how to apply + that the dashboard follows
 *
 * The picker section is NOT a target because it only renders in
 * multi/silo modes. Step 1's copy mentions that switching modes
 * reveals it, so users don't need a dedicated step.
 *
 * BUMP TOUR_VERSION when STEPS materially changes. Frontend gates
 * on `user.tour_state.scope < TOUR_VERSION`; bumping re-triggers
 * the tour for everyone whose stored value is lower.
 */

import { useDriverTour } from '@/hooks/useDriverTour';

export const TOUR_ID = 'scope';
export const TOUR_VERSION = 1;

const STEPS = [
  {
    element: '[data-tour="scope-mode"]',
    popover: {
      title: 'Pick a scope mode',
      description:
        "Three modes control which topics drive your daily content. " +
        "'All' uses every active topic. 'Multi-select' lets you pick a subset. " +
        "'Silo' focuses everything on one topic. Switching to Multi or Silo " +
        "reveals a topic picker below.",
      side: 'bottom' as const,
      align: 'start' as const,
    },
  },
  {
    element: '[data-tour="scope-save"]',
    popover: {
      title: 'Save to apply',
      description:
        "Hit Save and your dashboard immediately follows the new scope — " +
        "today's paper, topic review, and quiz all use your updated picks " +
        "on the next refresh.",
      side: 'top' as const,
      align: 'end' as const,
    },
  },
];

export default function ScopeTour() {
  useDriverTour({
    tour_id: TOUR_ID,
    version: TOUR_VERSION,
    fire_on_path: '/settings/scope',
    steps: STEPS,
  });
  return null;
}
