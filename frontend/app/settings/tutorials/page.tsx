'use client';

/**
 * /settings/tutorials — replay any product tour on demand.
 *
 * Single source of truth for the tour list, replacing the picker UI that
 * used to be duplicated three times (Sidebar's HelpGroup, MobileTabBar's
 * helpView, and the old TourReplayCard on the account page). Replaying a
 * tour zeroes its tour_state on the server, refreshes /auth/me so the
 * in-memory auth state matches before navigating (otherwise the target
 * page's driver-tour hook could gate on the stale, already-seen value),
 * then routes to fire_on_path — useDriverTour fires the tour there via an
 * exact pathname match.
 */

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { resetTour } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

// keep in sync with KNOWN_TOUR_IDS on the backend
type TourChoice = { id: 'dashboard' | 'scope' | 'topics'; label: string; description: string; fire_on_path: string };
const TOUR_CHOICES: TourChoice[] = [
  { id: 'dashboard', label: 'Dashboard tour', description: 'Your daily reading queue and progress at a glance.', fire_on_path: '/' },
  { id: 'scope', label: 'Scope library tour', description: 'How scopes drive discovery, reviews, and quizzes.', fire_on_path: '/settings/scope/library' },
  { id: 'topics', label: 'Topics tour', description: 'Browsing and managing the topics catalog.', fire_on_path: '/topics' },
];

const PlayIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
    <path d="M8 12l2 2 6-6M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default function TutorialsPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function replay(choice: TourChoice) {
    if (busy) return;
    setBusy(choice.id);
    setError(null);
    try {
      await resetTour(choice.id);
      await refresh();
      router.push(choice.fire_on_path);
    } catch (e: any) {
      setError(e?.message || `Failed to replay the ${choice.label.toLowerCase()}`);
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif text-3xl font-semibold text-ink">Tutorials</h1>
        <p className="mt-1 text-ink-2">
          Replay any product tour. Each one fires the moment you land on its page.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">
          {error}
        </div>
      )}

      <ul className="space-y-2">
        {TOUR_CHOICES.map((choice) => {
          const loading = busy === choice.id;
          return (
            <li
              key={choice.id}
              className="flex items-center justify-between gap-4 rounded-lg border border-rule bg-paper-2 p-4"
            >
              <div className="min-w-0">
                <h2 className="font-serif text-[16px] font-semibold text-ink">{choice.label}</h2>
                <p className="mt-0.5 text-sm text-muted">{choice.description}</p>
              </div>
              <button
                type="button"
                onClick={() => replay(choice)}
                disabled={!!busy}
                aria-busy={loading}
                className="flex flex-shrink-0 items-center gap-2 rounded-lg border border-rule bg-paper px-4 py-2 text-sm font-medium text-ink-2 hover:bg-paper-3 disabled:opacity-50"
              >
                <PlayIcon />
                {loading ? 'Loading…' : 'Replay'}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
