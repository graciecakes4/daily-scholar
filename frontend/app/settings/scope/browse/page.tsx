'use client';

/**
 * /settings/scope/browse — browse public scopes from other users and starter
 * scopes from the system catalog.
 *
 * Two ways to start using a public scope:
 *   • Fork → makes a private copy in your library that you can edit
 *   • Use directly → sets it as your active scope without copying; the
 *     owner's edits propagate to you live, but you can't change it
 *
 * For private scopes, paste the ID into the "Request access by ID" form
 * at the bottom; the owner gets a request in their inbox and decides.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  searchPublicScopes,
  forkScope,
  setActiveScope,
  requestScopeAccess,
  type Scope,
} from '@/lib/api';

export default function ScopeBrowsePage() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Scope[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // initial load: with no query, show the top public scopes (starter +
  // most recent) so the page isn't empty on arrival
  useEffect(() => {
    (async () => {
      try {
        const rows = await searchPublicScopes();
        setResults(rows);
      } catch (e: any) {
        setError(e?.message || 'Failed to load scopes');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // debounced search on subsequent keystrokes
  useEffect(() => {
    const q = query.trim();
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await searchPublicScopes(q || undefined);
        setResults(rows);
      } catch (e: any) {
        setError(e?.message || 'Search failed');
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  async function onFork(s: Scope) {
    setBusyId(s.id); setError(null); setSuccess(null);
    try {
      const fk = await forkScope(s.id);
      router.push(`/settings/scope/${fk.id}`);
    } catch (e: any) {
      setError(e?.message || 'Fork failed');
      setBusyId(null);
    }
  }

  async function onUseDirectly(s: Scope) {
    setBusyId(s.id); setError(null); setSuccess(null);
    try {
      await setActiveScope(s.id);
      setSuccess(`"${s.name}" is now your active scope.`);
    } catch (e: any) {
      setError(e?.message || 'Failed to set active');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif italic text-3xl font-bold text-ink">Browse public scopes</h1>
        <p className="text-muted mt-1">
          Starter scopes and public scopes shared by other users. Fork one to
          edit, or use it directly to track the owner's changes live.
        </p>
      </header>

      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded-xl px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-moss/5 border border-moss/25 text-moss rounded-xl px-4 py-2 text-sm">
          {success}
        </div>
      )}

      {/* search */}
      <div>
        <input
          type="search"
          placeholder="Search by name or description…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="w-full px-4 py-2 border border-rule rounded-xl bg-paper text-ink text-sm"
        />
      </div>

      {/* results */}
      <section className="space-y-3">
        {loading ? (
          <p className="text-sm text-muted">Searching…</p>
        ) : !results || results.length === 0 ? (
          <p className="text-sm text-muted italic">
            No public scopes match. Try a different search.
          </p>
        ) : (
          <ul className="space-y-2">
            {results.map(s => (
              <PublicScopeRow
                key={s.id}
                scope={s}
                busy={busyId === s.id}
                onFork={() => onFork(s)}
                onUseDirectly={() => onUseDirectly(s)}
              />
            ))}
          </ul>
        )}
      </section>

      {/* request access by id */}
      <RequestByIdSection
        onSuccess={msg => { setSuccess(msg); setError(null); }}
        onError={msg => { setError(msg); setSuccess(null); }}
      />
    </div>
  );
}

function PublicScopeRow({
  scope, busy, onFork, onUseDirectly,
}: {
  scope: Scope;
  busy: boolean;
  onFork: () => void;
  onUseDirectly: () => void;
}) {
  const isStarter = scope.owner_user_id === null;
  return (
    <li className="bg-paper-2 border border-rule rounded-2xl p-4 flex items-start gap-3 flex-wrap shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)]">
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={`/settings/scope/${scope.id}`}
            className="font-medium text-ink hover:underline truncate"
          >
            {scope.name}
          </Link>
          {isStarter ? (
            <span className="text-xs bg-gold/10 text-gold-dark border border-gold/30 rounded px-1.5 py-0.5">
              starter
            </span>
          ) : (
            <span className="text-xs bg-moss/10 text-moss border border-moss/30 rounded px-1.5 py-0.5">
              public
            </span>
          )}
          {scope.forked_from_scope_id && (
            <span className="text-xs text-muted">
              forked from #{scope.forked_from_scope_id}
            </span>
          )}
        </div>
        {scope.description && (
          <p className="text-sm text-ink-2 mt-1">{scope.description}</p>
        )}
        <div className="text-xs text-muted mt-1">
          <span className="font-mono">{scope.scope_mode}</span>
          {' · '}
          {scope.scope_topic_ids.length} topic(s)
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={onUseDirectly}
          disabled={busy}
          className="text-sm px-3 py-1.5 bg-paper-3 text-ink-2 rounded-full hover:bg-rule/60 disabled:opacity-50"
          title="Use this scope as-is — owner's edits propagate live, but you can't change it"
        >
          Use directly
        </button>
        <button
          type="button"
          onClick={onFork}
          disabled={busy}
          className="text-sm px-3 py-1.5 bg-gold-dark text-white rounded-full hover:bg-[#734f14] disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Fork'}
        </button>
      </div>
    </li>
  );
}

function RequestByIdSection({
  onSuccess, onError,
}: {
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [id, setId] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    const parsed = Number(id);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      onError('Scope id must be a positive number.');
      return;
    }
    setBusy(true);
    try {
      await requestScopeAccess(parsed, message || undefined);
      onSuccess('Request sent. The owner will see it in their inbox.');
      setId('');
      setMessage('');
    } catch (e: any) {
      onError(e?.message || 'Request failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-paper-2 border border-rule rounded-2xl p-5 space-y-3">
      <div>
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-muted">
          Request access by ID
        </h2>
        <p className="text-xs text-muted mt-1">
          For private scopes that aren't in public search. If someone gave you a
          scope ID, paste it here and the owner will see your request.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="number"
          placeholder="Scope ID"
          value={id}
          onChange={e => setId(e.target.value)}
          className="px-3 py-2 border border-rule rounded-xl text-sm w-32 bg-paper text-ink"
        />
        <input
          type="text"
          placeholder="Message (optional)"
          value={message}
          onChange={e => setMessage(e.target.value)}
          maxLength={2000}
          className="flex-grow px-3 py-2 border border-rule rounded-xl text-sm bg-paper text-ink"
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || !id.trim()}
          className="text-sm px-4 py-2 bg-gold-dark text-white rounded-full hover:bg-[#734f14] disabled:opacity-50"
        >
          {busy ? 'Sending…' : 'Request access'}
        </button>
      </div>
    </section>
  );
}
