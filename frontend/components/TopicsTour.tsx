'use client';

/**
 * Tutorial for /topics — the topic catalog.
 *
 * 3 steps targeting elements that always exist (regardless of how many
 * topics the user has):
 *   1. "+ New topic" — how to create
 *   2. "Discover" — how to subscribe to others' public topics
 *   3. Filter row — how to find a topic in a long list
 *
 * We deliberately don't target individual topic rows — they may not
 * exist for brand-new accounts who skipped the onboarding wizard,
 * and pointing at "your topics show up here" without an actual row
 * to highlight feels weird. The new/discover/filter trio covers the
 * actions a user needs to learn.
 *
 * BUMP TOUR_VERSION when STEPS materially changes. Frontend gates on
 * `user.tour_state.topics < TOUR_VERSION`; bumping re-triggers the
 * tour for everyone whose stored value is lower.
 */

import { useDriverTour } from '@/hooks/useDriverTour';

export const TOUR_ID = 'topics';
export const TOUR_VERSION = 1;

const STEPS = [
  {
    element: '[data-tour="topics-new"]',
    popover: {
      title: 'Create a new topic',
      description:
        "A topic is a bundle of keywords + arXiv categories + key concepts. " +
        "It's what drives paper discovery and review/quiz generation. Click " +
        "here to make one from scratch, or let the onboarding wizard generate " +
        "one for you from a description.",
      side: 'bottom' as const,
      align: 'end' as const,
    },
  },
  {
    element: '[data-tour="topics-discover"]',
    popover: {
      title: 'Discover topics from other users',
      description:
        "Other users can mark their topics public. Discover lets you search " +
        "them and subscribe — subscribed topics appear in your scope and stay " +
        "live (when the owner updates the keywords, your paper discovery " +
        "follows along automatically).",
      side: 'bottom' as const,
      align: 'end' as const,
    },
  },
  {
    element: '[data-tour="topics-filter"]',
    popover: {
      title: 'Filter + manage your topics',
      description:
        "Filter the list by stream, or hide orphaned topics whose YAML file " +
        "is gone. Each row shows owner ('System', 'Yours', or 'Subscribed'), " +
        "keyword + concept counts, and edit / deactivate / delete actions on " +
        "topics you own.",
      side: 'bottom' as const,
      align: 'start' as const,
    },
  },
];

export default function TopicsTour() {
  useDriverTour({
    tour_id: TOUR_ID,
    version: TOUR_VERSION,
    fire_on_path: '/topics',
    steps: STEPS,
  });
  return null;
}
