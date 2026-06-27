'use client';

/**
 * /scopes/requests — access-request inbox.
 *
 * Two sections:
 *   • Incoming — requests targeted at scopes I own. Pending ones have
 *     Approve / Deny buttons. Approving inserts a ScopeAccessGrant so
 *     the requester can view (but not edit) the scope.
 *   • Outgoing — requests I've submitted, with current status.
 *
 * For incoming requests, the page also fetches the owned scope rows so
 * each request renders with the scope's name instead of just its id.
 * Outgoing requests show "Scope #N" since the caller might not be able
 * to view the scope until approval.
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  listIncomingAccessRequests,
  listOutgoingAccessRequests,
  decideAccessRequest,
  listMyScopes,
  type ScopeAccessRequest,
  type AccessRequestStatus,
  type LibraryItem,
} from '@/lib/api';

type StatusFilter = AccessRequestStatus | 'all';

export default function AccessRequestsPage() {
  const [incoming, setIncoming] = useState<ScopeAccessRequest[]>([]);
  const [outgoing, setOutgoing] = useState<ScopeAccessRequest[]>([]);
  const [scopeNames, setScopeNames] = useState<Record<number, string>>({});
  const [incomingFilter, setIncomingFilter] = useState<StatusFilter>('pending');
  const [outgoingFilter, setOutgoingFilter] = useState<StatusFilter>('all');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function load() {
    try {
      const [inc, out, lib] = await Promise.all([
        listIncomingAccessRequests(incomingFilter),
        listOutgoingAccessRequests(outgoingFilter === 'all' ? undefined : outgoingFilter),
        listMyScopes(),
      ]);
      setIncoming(inc);
      setOutgoing(out);
      // build scope_id -> name map from owned scopes (incoming requests
      // only target owned scopes, so this covers every incoming row)
      const names: Record<number, string> = {};
      for (const item of lib) names[item.id] = item.name;
      setScopeNames(names);
    } catch (e: any) {
      setError(e?.message || 'Failed to load requests');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [incomingFilter, outgoingFilter]);

  async function decide(req: ScopeAccessRequest, decision: 'approve' | 'deny') {
    setBusyId(req.id); setError(null); setSuccess(null);
    try {
      await decideAccessRequest(req.id, decision);
      setSuccess(
        decision === 'approve'
          ? 'Approved — the requester now has view access.'
          : 'Denied.'
      );
      await load();
    } catch (e: any) {
      setError(e?.message || `Failed to ${decision}`);
    } finally {
      setBusyId(null);
    }
  }

  if (loading && incoming.length === 0 && outgoing.length === 0) {
    return <div className="text-slate-500">Loading…</div>;
  }

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Access requests</h1>
          <p className="text-slate-600 mt-1">
            Approve or deny requests for your private scopes, and track the requests you've sent.
          </p>
        </div>
        <nav className="text-sm flex gap-4">
          <Link href="/settings/scope" className="text-sky-700 hover:underline">
            ← My library
          </Link>
          <Link href="/scopes/browse" className="text-sky-700 hover:underline">
            Browse public →
          </Link>
        </nav>
      </header>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-2 text-sm">
          {success}
        </div>
      )}

      {/* incoming */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
            Incoming ({incoming.length})
          </h2>
          <StatusFilterTabs value={incomingFilter} onChange={setIncomingFilter} />
        </div>
        {incoming.length === 0 ? (
          <p className="text-sm text-slate-500 italic">
            No {incomingFilter === 'all' ? '' : incomingFilter + ' '}requests right now.
          </p>
        ) : (
          <ul className="space-y-2">
            {incoming.map(r => (
              <IncomingRow
                key={r.id}
                req={r}
                scopeName={scopeNames[r.scope_id]}
                busy={busyId === r.id}
                onDecide={(d) => decide(r, d)}
              />
            ))}
          </ul>
        )}
      </section>

      {/* outgoing */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
            Outgoing ({outgoing.length})
          </h2>
          <StatusFilterTabs value={outgoingFilter} onChange={setOutgoingFilter} />
        </div>
        {outgoing.length === 0 ? (
          <p className="text-sm text-slate-500 italic">
            You haven't requested access to anything{outgoingFilter !== 'all' ? ` (${outgoingFilter})` : ''}.
          </p>
        ) : (
          <ul className="space-y-2">
            {outgoing.map(r => (
              <OutgoingRow key={r.id} req={r} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function StatusFilterTabs({
  value, onChange,
}: {
  value: StatusFilter;
  onChange: (v: StatusFilter) => void;
}) {
  const options: StatusFilter[] = ['pending', 'approved', 'denied', 'all'];
  return (
    <div className="flex gap-1 text-xs">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={`px-2 py-1 rounded ${
            value === opt
              ? 'bg-slate-900 text-white'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function IncomingRow({
  req, scopeName, busy, onDecide,
}: {
  req: ScopeAccessRequest;
  scopeName?: string;
  busy: boolean;
  onDecide: (d: 'approve' | 'deny') => void;
}) {
  const pending = req.status === 'pending';
  return (
    <li className="bg-white border border-slate-200 rounded-lg p-4 flex items-start gap-3 flex-wrap">
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href={`/settings/scope/${req.scope_id}`}
            className="font-medium text-slate-900 hover:underline truncate"
          >
            {scopeName || `Scope #${req.scope_id}`}
          </Link>
          <StatusBadge status={req.status} />
        </div>
        <p className="text-sm text-slate-700 mt-1">
          <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">
            {req.requester_user_id}
          </code>
          {' requested access'}
          {req.message && (
            <>: <span className="text-slate-600">&ldquo;{req.message}&rdquo;</span></>
          )}
        </p>
        <div className="text-xs text-slate-500 mt-1">
          {new Date(req.created_at).toLocaleString()}
          {req.decided_at && (
            <> · decided {new Date(req.decided_at).toLocaleString()}</>
          )}
        </div>
      </div>
      {pending && (
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => onDecide('deny')}
            disabled={busy}
            className="text-sm px-3 py-1.5 text-rose-600 hover:bg-rose-50 rounded disabled:opacity-50"
          >
            Deny
          </button>
          <button
            type="button"
            onClick={() => onDecide('approve')}
            disabled={busy}
            className="text-sm px-3 py-1.5 bg-slate-900 text-white rounded hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? 'Working…' : 'Approve'}
          </button>
        </div>
      )}
    </li>
  );
}

function OutgoingRow({ req }: { req: ScopeAccessRequest }) {
  const viewable = req.status === 'approved';
  return (
    <li className="bg-white border border-slate-200 rounded-lg p-4 flex items-start gap-3 flex-wrap">
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {viewable ? (
            <Link
              href={`/settings/scope/${req.scope_id}`}
              className="font-medium text-slate-900 hover:underline"
            >
              Scope #{req.scope_id}
            </Link>
          ) : (
            <span className="font-medium text-slate-900">Scope #{req.scope_id}</span>
          )}
          <StatusBadge status={req.status} />
        </div>
        {req.message && (
          <p className="text-sm text-slate-600 mt-1">
            Your message: &ldquo;{req.message}&rdquo;
          </p>
        )}
        <div className="text-xs text-slate-500 mt-1">
          requested {new Date(req.created_at).toLocaleString()}
          {req.decided_at && (
            <> · decided {new Date(req.decided_at).toLocaleString()}</>
          )}
        </div>
      </div>
    </li>
  );
}

function StatusBadge({ status }: { status: AccessRequestStatus }) {
  const styles: Record<AccessRequestStatus, string> = {
    pending:  'bg-amber-50 text-amber-700 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    denied:   'bg-rose-50 text-rose-700 border-rose-200',
  };
  return (
    <span className={`text-xs border rounded px-1.5 py-0.5 ${styles[status]}`}>
      {status}
    </span>
  );
}
