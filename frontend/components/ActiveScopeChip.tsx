'use client';

/**
 * ActiveScopeChip — the pinned chip at the top of the left rail that
 * surfaces the user's currently active scope (name, topic count, a
 * "Change scope" affordance).
 *
 * Self-fetches via getActiveScope() on mount. Renders nothing while the
 * fetch is in flight, a quiet "pick a scope" prompt if the user has none
 * yet, and gracefully bails out (returns null) on auth errors so the
 * sidebar still works for logged-out users hitting public routes.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getActiveScope, type Scope } from '@/lib/api';

type LoadState = 'loading' | 'ready' | 'empty' | 'error';

// turn a UTC iso timestamp into a short human stamp ("just now",
// "6h ago", "yesterday", "3d ago", or a date for anything older).
// kept inline because no other component currently needs relative-time
// formatting and pulling in date-fns isn't worth the bundle weight.
function formatRelative(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const diffMs = Date.now() - then;
  // clamp negative values (clock skew) to "just now" so we never claim
  // a scope was edited in the future
  if (diffMs < 0) return 'just now';
  const sec = Math.floor(diffMs / 1000);
  if (sec < 45) return 'just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day === 1) return 'yesterday';
  if (day < 7) return `${day}d ago`;
  // older than a week — show a compact date so users can read it
  return new Date(then).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function ActiveScopeChip() {
  const [scope, setScope] = useState<Scope | null>(null);
  const [state, setState] = useState<LoadState>('loading');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getActiveScope();
        if (cancelled) return;
        if (s) {
          setScope(s);
          setState('ready');
        } else {
          setState('empty');
        }
      } catch {
        // 401 / network — render nothing rather than crash the rail
        if (!cancelled) setState('error');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (state === 'loading' || state === 'error') {
    // reserve roughly the same height so the rail doesn't jump on hydrate
    return <div className="mx-1.5 mb-5 h-[88px] rounded-[10px] bg-paper-2/60 border border-rule/60 animate-pulse" aria-hidden />;
  }

  if (state === 'empty') {
    return (
      <Link
        href="/scopes/picker"
        className="group relative mx-1.5 mb-5 block rounded-[10px] border border-rule bg-paper-2 px-3.5 pt-3 pb-3.5 hover:bg-paper-3 transition-colors"
      >
        <div className="font-serif text-[10px] font-medium uppercase tracking-[0.18em] text-muted">No active scope</div>
        <div className="font-serif text-[15px] font-semibold leading-tight mt-0.5 text-ink">Pick a scope to begin</div>
        <span className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-gold-dark">
          Choose one
          <span aria-hidden>→</span>
        </span>
      </Link>
    );
  }

  // scope.scope_topic_ids is always an array (backend guarantees), but defensive
  const topicCount = scope?.scope_topic_ids?.length ?? 0;
  // updated_at reflects scope edits, not discovery refreshes — use the
  // verb "edited" so we don't mislead users about pipeline activity
  const editedStamp = scope?.updated_at ? formatRelative(scope.updated_at) : '';
  const editedLabel = editedStamp ? `edited ${editedStamp}` : '';

  return (
    <div className="relative mx-1.5 mb-5 overflow-hidden rounded-[10px] border border-rule px-3.5 py-3"
         style={{ background: 'linear-gradient(180deg, #FBF6EB, #F1E8D2)' }}>
      {/* diagonal hatching — same trick as the mockup */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ backgroundImage: 'repeating-linear-gradient(135deg, transparent 0 8px, rgba(181,134,43,0.05) 8px 9px)' }}
      />
      <div className="relative">
        <div className="font-serif text-[10px] font-medium uppercase tracking-[0.18em] text-muted">In scope</div>
        <div className="font-serif text-[15px] font-semibold leading-tight mt-0.5 mb-1 text-ink truncate" title={scope!.name}>
          {scope!.name}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-moss" aria-hidden />
          <span>{topicCount} {topicCount === 1 ? 'topic' : 'topics'}{editedLabel ? ` · ${editedLabel}` : ''}</span>
        </div>
        <Link
          href="/settings/scope/library"
          className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-gold-dark hover:text-ink transition-colors"
        >
          Change scope
          <span aria-hidden>→</span>
        </Link>
      </div>
    </div>
  );
}
