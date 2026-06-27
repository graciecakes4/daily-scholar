'use client';

/**
 * /scopes/picker — first-run scope picker for users with no active scope.
 *
 * Per the scope-library design: new users land here (via ScopePickerGuard)
 * until they pick an active scope. Three paths off this page:
 *
 *   • Use a starter — sets it as active without copying, so the user
 *     immediately gets curated content driven by a system-maintained scope.
 *     They can fork later from /settings/scope if they want to edit.
 *   • Browse all public scopes — wider catalog including other users' public
 *     scopes, not just the system starters.
 *   • Start from scratch — creates an empty private scope, sets it active,
 *     and routes the user to the editor to fill it in.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  searchPublicScopes,
  setActiveScope,
  createScope,
  type Scope,
} from '@/lib/api';

export default function ScopePickerPage() {
  const router = useRouter();
  const [starters, setStarters] = useState<Scope[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // pull a wide first page; the starter scopes are system-owned
        // (owner_user_id === null), so we filter to just those.
        const all = await searchPublicScopes(undefined, 100);
        setStarters(all.filter(s => s.owner_user_id === null));
      } catch (e: any) {
        setError(e?.message || 'Failed to load starter scopes');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function useStarter(s: Scope) {
    setBusy(true); setError(null);
    try {
      await setActiveScope(s.id);
      router.push('/');
    } catch (e: any) {
      setError(e?.message || 'Failed to set active scope');
      setBusy(false);
    }
  }

  async function startFromScratch() {
    setBusy(true); setError(null);
    try {
      const fresh = await createScope({
        name: 'My scope',
        scope_mode: 'all',
        scope_topic_ids: [],
        visibility: 'private',
      });
      await setActiveScope(fresh.id);
      router.push(`/settings/scope/${fresh.id}`);
    } catch (e: any) {
      setError(e?.message || 'Failed to create scope');
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">Pick a scope to start</h1>
        <p className="text-slate-600 mt-2 max-w-2xl">
          A scope decides which topics drive your daily papers, reviews, and
          quizzes. Pick a starter from the catalog below, browse what others
          have published, or build one from scratch — you can always switch
          later.
        </p>
      </header>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* starter scopes */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Starter scopes
        </h2>
        {loading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : starters.length === 0 ? (
          <p className="text-sm text-slate-500 italic">
            No starter scopes available right now.
          </p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {starters.map(s => (
              <StarterCard
                key={s.id}
                scope={s}
                busy={busy}
                onPick={() => useStarter(s)}
              />
            ))}
          </ul>
        )}
      </section>

      {/* secondary paths */}
      <section className="bg-slate-50 border border-slate-200 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Or…
        </h2>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            href="/scopes/browse"
            className="flex-1 px-4 py-3 bg-white border border-slate-300 rounded-lg text-sm text-center hover:bg-slate-50"
          >
            Browse all public scopes
            <div className="text-xs text-slate-500 mt-0.5">
              Including scopes shared by other users
            </div>
          </Link>
          <button
            type="button"
            onClick={startFromScratch}
            disabled={busy}
            className="flex-1 px-4 py-3 bg-white border border-slate-300 rounded-lg text-sm text-center hover:bg-slate-50 disabled:opacity-50"
          >
            Start from scratch
            <div className="text-xs text-slate-500 mt-0.5">
              {busy ? 'Working…' : "Build your own scope from the topic catalog"}
            </div>
          </button>
        </div>
      </section>
    </div>
  );
}

function StarterCard({
  scope, busy, onPick,
}: {
  scope: Scope;
  busy: boolean;
  onPick: () => void;
}) {
  return (
    <li className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col gap-2">
      <div>
        <h3 className="font-medium text-slate-900">{scope.name}</h3>
        <div className="text-xs text-slate-500 mt-0.5">
          <span className="font-mono">{scope.scope_mode}</span>
          {' · '}
          {scope.scope_topic_ids.length} topic(s)
        </div>
      </div>
      {scope.description && (
        <p className="text-sm text-slate-600 flex-grow">{scope.description}</p>
      )}
      <button
        type="button"
        onClick={onPick}
        disabled={busy}
        className="mt-2 self-start px-4 py-2 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
      >
        {busy ? 'Working…' : 'Use this scope'}
      </button>
    </li>
  );
}
