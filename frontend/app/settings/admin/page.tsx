'use client';

/**
 * /settings/admin — minimum admin surface (Phase B slice of Phase F).
 *
 * Two tabs:
 *   - Pending approvals: list pending users + Approve / Reject buttons
 *   - Invite codes: generate, list, revoke, copy-to-clipboard
 *
 * Renders only when user.role === 'admin'. Non-admin browsers either
 * see the redirect to /login (if not logged in at all) or a "not
 * authorized" placeholder.
 */

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  approveUser,
  changeAccountRole,
  changeAccountStatus,
  createInvite,
  listAccounts,
  listInvites,
  listPendingApprovals,
  rejectUser,
  revokeInvite,
  type AccountSummary,
  type InviteState,
  type InviteSummary,
  type PendingUserSummary,
  type UserRole,
  type UserStatus,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type Tab = 'approvals' | 'invites' | 'users';

export default function AdminSettingsPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>('approvals');
  const currentUserId = user?.user_id ?? null;

  if (loading) return <div className="text-slate-500">Loading…</div>;

  if (!user) {
    return (
      <NotAuthorized message="You need to log in to view this page." />
    );
  }
  if (user.role !== 'admin') {
    return (
      <NotAuthorized message="You don't have admin access." />
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Admin</h1>
          <p className="text-slate-600 mt-1">
            Approve new signups and manage invite codes.
          </p>
        </div>
        <nav className="text-sm">
          <Link href="/settings/scope" className="text-sky-700 hover:underline">
            ← Settings
          </Link>
        </nav>
      </header>

      <div className="border-b border-slate-200">
        <nav className="-mb-px flex gap-1">
          <TabButton active={tab === 'approvals'} onClick={() => setTab('approvals')}>
            Pending approvals
          </TabButton>
          <TabButton active={tab === 'invites'} onClick={() => setTab('invites')}>
            Invite codes
          </TabButton>
          <TabButton active={tab === 'users'} onClick={() => setTab('users')}>
            Users
          </TabButton>
        </nav>
      </div>

      {tab === 'approvals' && <ApprovalsTab />}
      {tab === 'invites' && <InvitesTab />}
      {tab === 'users' && <UsersTab currentUserId={currentUserId} />}
    </div>
  );
}

// ---------- shared bits ----------

function TabButton({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
        active
          ? 'border-slate-900 text-slate-900'
          : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
      }`}
    >
      {children}
    </button>
  );
}

function NotAuthorized({ message }: { message: string }) {
  return (
    <div className="max-w-md mx-auto mt-12 bg-white border border-slate-200 rounded-lg p-6 text-center space-y-3">
      <h1 className="text-xl font-bold text-slate-900">Not authorized</h1>
      <p className="text-sm text-slate-600">{message}</p>
      <Link href="/" className="inline-block px-4 py-2 bg-slate-900 text-white rounded text-sm">
        Back to app
      </Link>
    </div>
  );
}

// ---------- approvals tab ----------

function ApprovalsTab() {
  const [items, setItems] = useState<PendingUserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listPendingApprovals();
      setItems(r.pending);
    } catch (e: any) {
      setError(e?.message || 'Failed to load pending approvals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function onApprove(id: number) {
    setBusyId(id);
    try {
      await approveUser(id);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Approve failed');
    } finally {
      setBusyId(null);
    }
  }

  async function onReject(id: number) {
    if (!confirm('Reject and delete this account? This cannot be undone.')) return;
    setBusyId(id);
    try {
      await rejectUser(id);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Reject failed');
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="text-slate-500">Loading pending users…</div>;

  return (
    <section className="space-y-3">
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}

      {items.length === 0 ? (
        <div className="text-sm text-slate-500 italic">No pending approvals.</div>
      ) : (
        <ul className="space-y-2">
          {items.map(u => (
            <li key={u.id} className="bg-white border border-slate-200 rounded-lg p-4 flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="font-medium text-slate-900 truncate">{u.email}</div>
                <div className="text-xs text-slate-500 truncate">
                  user_id: <code>{u.user_id}</code> · waiting {formatWaiting(u.waiting_seconds)}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => onApprove(u.id)}
                  disabled={busyId !== null}
                  className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => onReject(u.id)}
                  disabled={busyId !== null}
                  className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded text-sm hover:bg-rose-50 hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatWaiting(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

// ---------- invites tab ----------

function InvitesTab() {
  const [invites, setInvites] = useState<InviteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [expiresInDays, setExpiresInDays] = useState<string>('');     // '' = no expiry
  const [maxUses, setMaxUses] = useState<number>(1);
  const [copied, setCopied] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listInvites(true);
      setInvites(r.invites);
    } catch (e: any) {
      setError(e?.message || 'Failed to load invites');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const expires = expiresInDays.trim() ? Number(expiresInDays) : undefined;
      await createInvite({ expires_in_days: expires, max_uses: maxUses });
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Create failed');
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(id: number) {
    setBusyId(id);
    try {
      await revokeInvite(id);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Revoke failed');
    } finally {
      setBusyId(null);
    }
  }

  async function onCopy(code: string, id: number) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      // navigator.clipboard may not be available on non-HTTPS or older browsers
      setError("Couldn't copy — select the code and copy manually.");
    }
  }

  return (
    <section className="space-y-4">
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}

      {/* generate */}
      <form onSubmit={onCreate} className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Generate code</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Expires in (days)</label>
            <input
              type="number"
              min={1}
              max={365}
              placeholder="never"
              value={expiresInDays}
              onChange={e => setExpiresInDays(e.target.value)}
              className="w-32 px-3 py-1.5 border border-slate-300 rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Max uses</label>
            <input
              type="number"
              min={1}
              max={1000}
              value={maxUses}
              onChange={e => setMaxUses(Math.max(1, Number(e.target.value) || 1))}
              className="w-24 px-3 py-1.5 border border-slate-300 rounded text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-1.5 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
          >
            {creating ? 'Generating…' : 'Generate'}
          </button>
        </div>
      </form>

      {/* list */}
      {loading ? (
        <div className="text-slate-500">Loading invites…</div>
      ) : invites.length === 0 ? (
        <div className="text-sm text-slate-500 italic">No invite codes yet.</div>
      ) : (
        <ul className="space-y-2">
          {invites.map(inv => (
            <li key={inv.id} className="bg-white border border-slate-200 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                  <code className="font-mono text-sm bg-slate-100 px-2 py-1 rounded select-all truncate">
                    {inv.code}
                  </code>
                  <button
                    type="button"
                    onClick={() => onCopy(inv.code, inv.id)}
                    className="text-xs text-sky-700 hover:underline"
                  >
                    {copied === inv.id ? 'Copied!' : 'Copy'}
                  </button>
                  <StateBadge state={inv.state} />
                </div>
                {inv.state === 'available' && (
                  <button
                    onClick={() => onRevoke(inv.id)}
                    disabled={busyId !== null}
                    className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded text-xs hover:bg-rose-50 hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
                  >
                    Revoke
                  </button>
                )}
              </div>
              <div className="text-xs text-slate-500">
                {inv.uses} / {inv.max_uses} used
                {inv.expires_at ? ` · expires ${new Date(inv.expires_at).toLocaleString()}` : ' · never expires'}
                {inv.revoked_at ? ` · revoked ${new Date(inv.revoked_at).toLocaleString()}` : ''}
                {' · created '}{new Date(inv.created_at).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StateBadge({ state }: { state: InviteState }) {
  const styles: Record<InviteState, string> = {
    available: 'bg-emerald-100 text-emerald-800',
    exhausted: 'bg-slate-200 text-slate-700',
    expired: 'bg-amber-100 text-amber-800',
    revoked: 'bg-rose-100 text-rose-800',
  };
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-semibold ${styles[state]}`}>
      {state}
    </span>
  );
}

// ---------- users tab ----------

function UsersTab({ currentUserId }: { currentUserId: string | null }) {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<'' | UserStatus>('');
  const [roleFilter, setRoleFilter] = useState<'' | UserRole>('');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listAccounts({
        status: statusFilter || undefined,
        role: roleFilter || undefined,
      });
      setAccounts(rows);
    } catch (e: any) {
      setError(e?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, roleFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  async function onRole(u: AccountSummary, role: UserRole) {
    const verb = role === 'admin' ? 'Promote to admin' : 'Demote to user';
    if (!confirm(`${verb}: ${u.email}?`)) return;
    setBusyId(u.user_id);
    try {
      await changeAccountRole(u.user_id, role);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Role change failed');
    } finally {
      setBusyId(null);
    }
  }

  async function onStatus(u: AccountSummary, status: 'active' | 'suspended') {
    const verb = status === 'suspended'
      ? `Suspend ${u.email}? They'll be logged out of every device immediately.`
      : `Reactivate ${u.email}?`;
    if (!confirm(verb)) return;
    setBusyId(u.user_id);
    try {
      await changeAccountStatus(u.user_id, status);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Status change failed');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-4">
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}

      {/* filters */}
      <div className="bg-white border border-slate-200 rounded-lg p-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-slate-500">Status</label>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as '' | UserStatus)}
          className="text-sm border border-slate-300 rounded px-2 py-1"
        >
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="pending">Pending</option>
          <option value="suspended">Suspended</option>
        </select>
        <label className="text-xs text-slate-500 ml-2">Role</label>
        <select
          value={roleFilter}
          onChange={e => setRoleFilter(e.target.value as '' | UserRole)}
          className="text-sm border border-slate-300 rounded px-2 py-1"
        >
          <option value="">All</option>
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
        <span className="text-xs text-slate-400 ml-auto">{accounts.length} user(s)</span>
      </div>

      {loading ? (
        <div className="text-slate-500">Loading…</div>
      ) : accounts.length === 0 ? (
        <div className="text-sm text-slate-500 italic">No users match.</div>
      ) : (
        <ul className="space-y-2">
          {accounts.map(u => {
            const isSelf = currentUserId === u.user_id;
            const isPending = u.status === 'pending';
            // suspended users get a Reactivate button; active+pending get Suspend.
            // Pending is greyed out — they should go through approvals, not status edits.
            return (
              <li
                key={u.id}
                className="bg-white border border-slate-200 rounded-lg p-4 flex items-center justify-between gap-3 flex-wrap"
              >
                <div className="min-w-0 flex-grow">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-900 truncate">{u.email}</span>
                    <RoleBadge role={u.role} />
                    <StatusBadge status={u.status} />
                    {isSelf && (
                      <span className="text-[10px] uppercase tracking-wide bg-sky-100 text-sky-800 px-1.5 py-0.5 rounded font-semibold">
                        you
                      </span>
                    )}
                    {!u.onboarded && u.status === 'active' && (
                      <span className="text-[10px] uppercase tracking-wide bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-semibold">
                        un-onboarded
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    user_id: <code>{u.user_id}</code> · created {new Date(u.created_at).toLocaleDateString()}
                    {u.last_login_at && (
                      <> · last login {new Date(u.last_login_at).toLocaleDateString()}</>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {isPending ? (
                    <span className="text-xs text-slate-400 italic">use Approvals tab</span>
                  ) : (
                    <>
                      {u.role === 'user' ? (
                        <button
                          type="button"
                          onClick={() => onRole(u, 'admin')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded text-xs hover:bg-slate-50 disabled:opacity-50"
                        >
                          Promote
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onRole(u, 'user')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded text-xs hover:bg-slate-50 disabled:opacity-50"
                        >
                          Demote
                        </button>
                      )}
                      {u.status === 'active' ? (
                        <button
                          type="button"
                          onClick={() => onStatus(u, 'suspended')}
                          disabled={busyId !== null || isSelf}
                          title={isSelf ? "Can't suspend yourself" : 'Suspend this account'}
                          className="px-3 py-1.5 bg-white border border-rose-300 text-rose-700 rounded text-xs hover:bg-rose-50 disabled:opacity-50 disabled:hover:bg-white"
                        >
                          Suspend
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onStatus(u, 'active')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-emerald-600 text-white rounded text-xs font-medium hover:bg-emerald-700 disabled:opacity-50"
                        >
                          Reactivate
                        </button>
                      )}
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function RoleBadge({ role }: { role: UserRole }) {
  return role === 'admin' ? (
    <span className="text-[10px] uppercase tracking-wide bg-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-semibold">
      admin
    </span>
  ) : null;
}

function StatusBadge({ status }: { status: UserStatus }) {
  const map: Record<UserStatus, string> = {
    active: 'bg-emerald-100 text-emerald-800',
    pending: 'bg-amber-100 text-amber-800',
    suspended: 'bg-rose-100 text-rose-800',
  };
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-semibold ${map[status]}`}>
      {status}
    </span>
  );
}
