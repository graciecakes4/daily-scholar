'use client';

/**
 * My scopes — the list of scopes the user owns + has a grant for.
 *
 * Each scope is a saved, switchable view over the topics table. Exactly
 * one scope is active at a time; the active scope drives paper discovery,
 * topic review, and quizzes. Sibling destinations — browse public scopes,
 * incoming/outgoing access requests, and starting a new one — are peers
 * under Settings > Scope (see the Sidebar/MobileTabBar nav), not children
 * of this page, so there's no single "hub" this page has to fun.
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import {
  listMyScopes,
  getActiveScope,
  setActiveScope,
  deleteScope,
  type LibraryItem,
  type Scope,
} from '@/lib/api';

function MyScopesInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [active, setActive] = useState<Scope | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function load() {
    try {
      const [lib, act] = await Promise.all([
        listMyScopes(),
        getActiveScope(),
      ]);
      setLibrary(lib);
      setActive(act);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // the generate-scope wizard redirects here with ?created=<name> since
  // it doesn't have anywhere else on-brand to show a success message
  useEffect(() => {
    const created = searchParams.get('created');
    if (created) {
      setSuccess(`"${created}" created. It's in your library — set it active when you're ready.`);
      router.replace('/settings/scope/library');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function handleSetActive(id: number | null) {
    setBusy(true); setError(null); setSuccess(null);
    try {
      const next = await setActiveScope(id);
      setActive(next);
      setSuccess(id === null ? 'Active scope cleared.' : 'Active scope updated.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // route to the editor's "new" mode — no server-side row is created until
  // the user explicitly hits Save in the editor, so navigating away from
  // the editor without saving discards the draft.
  function handleCreate() {
    router.push('/settings/scope/new');
  }

  async function handleDelete(item: LibraryItem) {
    if (item.relation !== 'owned') return;
    if (!confirm(`Delete "${item.name}"? This cannot be undone.`)) return;
    setBusy(true); setError(null); setSuccess(null);
    try {
      await deleteScope(item.id);
      await load();
      setSuccess(`Deleted "${item.name}".`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="text-muted">Loading…</div>;

  const owned = library.filter(s => s.relation === 'owned');
  const granted = library.filter(s => s.relation === 'granted');

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif text-3xl font-bold text-ink">My scopes</h1>
        <p className="text-ink-2 mt-1">
          Saved views that decide which topics drive your discovery, reviews, and quizzes.
        </p>
      </header>

      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-moss/5 border border-moss/25 text-moss rounded-lg px-4 py-2 text-sm">
          {success}
        </div>
      )}

      {/* active scope banner */}
      <section
        data-tour="scope-active"
        className="bg-paper-2 border border-rule rounded-lg p-5 flex items-center justify-between gap-4 flex-wrap"
      >
        <div>
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
            Active scope
          </h2>
          {active ? (
            <div className="mt-1">
              <Link
                href={`/settings/scope/${active.id}`}
                className="text-lg font-medium text-ink hover:underline"
              >
                {active.name}
              </Link>
              <div className="text-xs text-muted mt-0.5">
                <span className="font-mono">{active.scope_mode}</span>
                {' · '}
                {active.scope_topic_ids.length} topic(s)
                {active.visibility === 'public' && ' · public'}
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-2 mt-1">
              No scope is active.{' '}
              <Link href="/settings/scope/browse" className="text-sky-700 hover:underline">
                Pick a starter
              </Link>
              {' '}or{' '}
              <Link
                href="/settings/scope/new"
                className="text-sky-700 hover:underline"
              >
                start from scratch
              </Link>
              .
            </p>
          )}
        </div>
        {active && (
          <button
            type="button"
            onClick={() => handleSetActive(null)}
            disabled={busy}
            className="text-xs text-muted hover:text-ink-2 underline disabled:opacity-50"
            title="Clear active scope"
          >
            Clear
          </button>
        )}
      </section>

      {/* my scopes */}
      <section data-tour="scope-library" className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
            My scopes ({owned.length})
          </h2>
          <div className="flex items-center gap-2">
            <Link
              href="/settings/scope/generate"
              className="text-sm px-4 py-2 border border-rule rounded-lg font-medium text-ink-2 hover:bg-paper"
              title="Describe what you want to study — keywords and arXiv categories are drafted for you"
            >
              Generate scope
            </Link>
            <button
              type="button"
              onClick={handleCreate}
              disabled={busy}
              className="px-4 py-2 bg-gold-dark text-white rounded-lg text-sm font-medium hover:bg-[#734f14] disabled:opacity-50"
            >
              {busy ? 'Working…' : 'New scope'}
            </button>
          </div>
        </div>
        {owned.length === 0 ? (
          <p className="text-sm text-muted italic">
            You haven't created any scopes yet. Fork a public starter, generate one from a
            description, or build one from scratch.
          </p>
        ) : (
          <ul className="space-y-2">
            {owned.map(s => (
              <LibraryRow
                key={s.id}
                item={s}
                isActive={active?.id === s.id}
                busy={busy}
                onSetActive={() => handleSetActive(s.id)}
                onDelete={() => handleDelete(s)}
              />
            ))}
          </ul>
        )}
      </section>

      {/* shared with me */}
      {granted.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
            Shared with me ({granted.length})
          </h2>
          <ul className="space-y-2">
            {granted.map(s => (
              <LibraryRow
                key={s.id}
                item={s}
                isActive={active?.id === s.id}
                busy={busy}
                onSetActive={() => handleSetActive(s.id)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default function MyScopesPage() {
  return (
    <Suspense fallback={<div className="text-muted">Loading…</div>}>
      <MyScopesInner />
    </Suspense>
  );
}

function LibraryRow({
  item, isActive, busy, onSetActive, onDelete,
}: {
  item: LibraryItem;
  isActive: boolean;
  busy: boolean;
  onSetActive: () => void;
  onDelete?: () => void;
}) {
  return (
    <li className={`bg-paper-2 border rounded-lg p-4 flex items-start gap-3 ${
      isActive ? 'border-ink ring-1 ring-ink/10' : 'border-rule'
    }`}>
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={`/settings/scope/${item.id}`}
            className="font-medium text-ink hover:underline truncate"
          >
            {item.name}
          </Link>
          <VisibilityBadge visibility={item.visibility} />
          {item.relation === 'granted' && (
            <span className="text-xs bg-sky-50 text-sky-700 border border-sky-200 rounded px-1.5 py-0.5">
              shared
            </span>
          )}
          {isActive && (
            <span className="text-xs bg-moss/5 text-moss border border-moss/25 rounded px-1.5 py-0.5">
              active
            </span>
          )}
          {item.forked_from_scope_id && (
            <span className="text-xs text-muted">
              forked from #{item.forked_from_scope_id}
            </span>
          )}
        </div>
        {item.description && (
          <p className="text-sm text-ink-2 mt-1 truncate">{item.description}</p>
        )}
        <div className="text-xs text-muted mt-1">
          <span className="font-mono">{item.scope_mode}</span>
          {' · '}
          {item.scope_topic_ids.length} topic(s)
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {!isActive && (
          <button
            type="button"
            onClick={onSetActive}
            disabled={busy}
            className="text-sm px-3 py-1.5 bg-paper-3 text-ink-2 rounded hover:bg-rule disabled:opacity-50"
          >
            Set active
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            disabled={busy}
            className="text-sm px-3 py-1.5 text-rust hover:bg-rust/5 rounded disabled:opacity-50"
          >
            Delete
          </button>
        )}
      </div>
    </li>
  );
}

function VisibilityBadge({ visibility }: { visibility: 'public' | 'private' }) {
  if (visibility === 'public') {
    return (
      <span className="text-xs bg-gold/5 text-gold-dark border border-gold/30 rounded px-1.5 py-0.5">
        public
      </span>
    );
  }
  return (
    <span className="text-xs bg-paper-3 text-ink-2 border border-rule rounded px-1.5 py-0.5">
      private
    </span>
  );
}
