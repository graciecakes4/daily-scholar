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
import PasswordStrength from '@/components/PasswordStrength';
import {
  adminResetPassword,
  approveUser,
  bustUserCache,
  changeAccountRole,
  changeAccountStatus,
  createInvite,
  exportTopicsToYaml,
  getQuizPerformanceStats,
  getStatsOverview,
  importTopicsFromYaml,
  listAccounts,
  listAuditEvents,
  listAuditEventTypes,
  listInvites,
  listPendingApprovals,
  listTopics,
  rejectUser,
  revokeInvite,
  type AccountSummary,
  type AuditEvent,
  type AuditEventType,
  type InviteState,
  type InviteSummary,
  type PendingUserSummary,
  type QuizPerformanceStats,
  type StatsOverview,
  type Topic,
  type UserRole,
  type UserStatus,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type Tab = 'approvals' | 'invites' | 'users' | 'audit' | 'topics' | 'cache' | 'stats';

export default function AdminSettingsPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>('approvals');
  const currentUserId = user?.user_id ?? null;

  if (loading) return <div className="text-muted">Loading…</div>;

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
      <header>
        <h1 className="text-3xl font-bold text-ink">Admin</h1>
        <p className="text-ink-2 mt-1">
          Approve new signups and manage invite codes.
        </p>
      </header>

      <div className="border-b border-rule">
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
          <TabButton active={tab === 'audit'} onClick={() => setTab('audit')}>
            Audit log
          </TabButton>
          <TabButton active={tab === 'topics'} onClick={() => setTab('topics')}>
            Topics
          </TabButton>
          <TabButton active={tab === 'cache'} onClick={() => setTab('cache')}>
            Cache
          </TabButton>
          <TabButton active={tab === 'stats'} onClick={() => setTab('stats')}>
            Stats
          </TabButton>
        </nav>
      </div>

      {tab === 'approvals' && <ApprovalsTab />}
      {tab === 'invites' && <InvitesTab />}
      {tab === 'users' && <UsersTab currentUserId={currentUserId} />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'topics' && <TopicsTab />}
      {tab === 'cache' && <CacheTab />}
      {tab === 'stats' && <StatsTab />}
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
          ? 'border-ink text-ink'
          : 'border-transparent text-muted hover:text-ink-2 hover:border-rule'
      }`}
    >
      {children}
    </button>
  );
}

function NotAuthorized({ message }: { message: string }) {
  return (
    <div className="max-w-md mx-auto mt-12 bg-paper-2 border border-rule rounded-lg p-6 text-center space-y-3">
      <h1 className="text-xl font-bold text-ink">Not authorized</h1>
      <p className="text-sm text-ink-2">{message}</p>
      <Link href="/" className="inline-block px-4 py-2 bg-gold-dark text-white rounded text-sm">
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

  if (loading) return <div className="text-muted">Loading pending users…</div>;

  return (
    <section className="space-y-3">
      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}

      {items.length === 0 ? (
        <div className="text-sm text-muted italic">No pending approvals.</div>
      ) : (
        <ul className="space-y-2">
          {items.map(u => (
            <li key={u.id} className="bg-paper-2 border border-rule rounded-lg p-4 flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="font-medium text-ink truncate">{u.email}</div>
                <div className="text-xs text-muted truncate">
                  user_id: <code>{u.user_id}</code> · waiting {formatWaiting(u.waiting_seconds)}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => onApprove(u.id)}
                  disabled={busyId !== null}
                  className="px-3 py-1.5 bg-moss text-white rounded text-sm font-medium hover:brightness-90 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => onReject(u.id)}
                  disabled={busyId !== null}
                  className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-sm hover:bg-rust/5 hover:border-rust/25 hover:text-rust disabled:opacity-50"
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
  const [customCode, setCustomCode] = useState<string>('');           // '' = auto-generate
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
      const code = customCode.trim() || undefined;
      await createInvite({ expires_in_days: expires, max_uses: maxUses, code });
      setCustomCode('');
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
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}

      {/* generate */}
      <form onSubmit={onCreate} className="bg-paper-2 border border-rule rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Generate code</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-muted mb-1">Expires in (days)</label>
            <input
              type="number"
              min={1}
              max={365}
              placeholder="never"
              value={expiresInDays}
              onChange={e => setExpiresInDays(e.target.value)}
              className="bg-paper text-ink w-32 px-3 py-1.5 border border-rule rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Max uses</label>
            <input
              type="number"
              min={1}
              max={1000}
              value={maxUses}
              onChange={e => setMaxUses(Math.max(1, Number(e.target.value) || 1))}
              className="bg-paper text-ink w-24 px-3 py-1.5 border border-rule rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Custom code</label>
            <input
              type="text"
              placeholder="leave blank for random"
              value={customCode}
              onChange={e => setCustomCode(e.target.value)}
              maxLength={32}
              className="bg-paper text-ink w-48 px-3 py-1.5 border border-rule rounded text-sm font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-1.5 bg-gold-dark text-white rounded text-sm font-medium hover:bg-[#734f14] disabled:opacity-50"
          >
            {creating ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>

      {/* list */}
      {loading ? (
        <div className="text-muted">Loading invites…</div>
      ) : invites.length === 0 ? (
        <div className="text-sm text-muted italic">No invite codes yet.</div>
      ) : (
        <ul className="space-y-2">
          {invites.map(inv => (
            <li key={inv.id} className="bg-paper-2 border border-rule rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 min-w-0">
                  <code className="font-mono text-sm bg-paper-3 px-2 py-1 rounded select-all truncate">
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
                    className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-xs hover:bg-rust/5 hover:border-rust/25 hover:text-rust disabled:opacity-50"
                  >
                    Revoke
                  </button>
                )}
              </div>
              <div className="text-xs text-muted">
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
    available: 'bg-moss/10 text-moss',
    exhausted: 'bg-rule text-ink-2',
    expired: 'bg-gold/10 text-gold-dark',
    revoked: 'bg-rust/10 text-rust',
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
  const [resetTarget, setResetTarget] = useState<AccountSummary | null>(null);

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
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}

      {/* filters */}
      <div className="bg-paper-2 border border-rule rounded-lg p-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-muted">Status</label>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as '' | UserStatus)}
          className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1"
        >
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="pending">Pending</option>
          <option value="suspended">Suspended</option>
        </select>
        <label className="text-xs text-muted ml-2">Role</label>
        <select
          value={roleFilter}
          onChange={e => setRoleFilter(e.target.value as '' | UserRole)}
          className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1"
        >
          <option value="">All</option>
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </select>
        <span className="text-xs text-muted ml-auto">{accounts.length} user(s)</span>
      </div>

      {loading ? (
        <div className="text-muted">Loading…</div>
      ) : accounts.length === 0 ? (
        <div className="text-sm text-muted italic">No users match.</div>
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
                className="bg-paper-2 border border-rule rounded-lg p-4 flex items-center justify-between gap-3 flex-wrap"
              >
                <div className="min-w-0 flex-grow">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-ink truncate">{u.email}</span>
                    <RoleBadge role={u.role} />
                    <StatusBadge status={u.status} />
                    {isSelf && (
                      <span className="text-[10px] uppercase tracking-wide bg-sky-100 text-sky-800 px-1.5 py-0.5 rounded font-semibold">
                        you
                      </span>
                    )}
                    {!u.onboarded && u.status === 'active' && (
                      <span className="text-[10px] uppercase tracking-wide bg-gold/10 text-gold-dark px-1.5 py-0.5 rounded font-semibold">
                        un-onboarded
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted truncate">
                    user_id: <code>{u.user_id}</code> · created {new Date(u.created_at).toLocaleDateString()}
                    {u.last_login_at && (
                      <> · last login {new Date(u.last_login_at).toLocaleDateString()}</>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {isPending ? (
                    <span className="text-xs text-muted italic">use Approvals tab</span>
                  ) : (
                    <>
                      {u.role === 'user' ? (
                        <button
                          type="button"
                          onClick={() => onRole(u, 'admin')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-xs hover:bg-paper disabled:opacity-50"
                        >
                          Promote
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onRole(u, 'user')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-xs hover:bg-paper disabled:opacity-50"
                        >
                          Demote
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setResetTarget(u)}
                        disabled={busyId !== null || isSelf}
                        title={isSelf ? 'Use Settings → Account to change your own password' : 'Set a new temporary password'}
                        className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-xs hover:bg-paper disabled:opacity-50 disabled:hover:bg-paper-2"
                      >
                        Reset password
                      </button>
                      {u.status === 'active' ? (
                        <button
                          type="button"
                          onClick={() => onStatus(u, 'suspended')}
                          disabled={busyId !== null || isSelf}
                          title={isSelf ? "Can't suspend yourself" : 'Suspend this account'}
                          className="px-3 py-1.5 bg-paper-2 border border-rust/25 text-rust rounded text-xs hover:bg-rust/5 disabled:opacity-50 disabled:hover:bg-paper-2"
                        >
                          Suspend
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onStatus(u, 'active')}
                          disabled={busyId !== null}
                          className="px-3 py-1.5 bg-moss text-white rounded text-xs font-medium hover:brightness-90 disabled:opacity-50"
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

      {resetTarget && (
        <ResetPasswordModal
          target={resetTarget}
          onClose={() => setResetTarget(null)}
          onDone={() => {
            setResetTarget(null);
            // no list reload needed — password change doesn't affect the
            // visible row fields, just kicks the user out of their sessions
          }}
          onError={msg => setError(msg)}
        />
      )}
    </section>
  );
}

function ResetPasswordModal({
  target, onClose, onDone, onError,
}: {
  target: AccountSummary;
  onClose: () => void;
  onDone: () => void;
  onError: (msg: string) => void;
}) {
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const tooShort = pw.length > 0 && pw.length < 8;
  const mismatch = confirm.length > 0 && pw !== confirm;
  const disabled = busy || pw.length < 8 || pw !== confirm;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await adminResetPassword(target.user_id, pw);
      // give the admin a chance to copy the password before the modal closes
      // (we don't generate it, the admin types it, so they likely have it
      // somewhere already — but the copy button is here for convenience)
      try {
        await navigator.clipboard.writeText(pw);
        setCopied(true);
      } catch { /* clipboard not available; admin still has it in the field */ }
      setTimeout(() => {
        onDone();
      }, copied ? 800 : 0);
    } catch (e: any) {
      onError(e?.message || 'Reset failed');
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <form
        onSubmit={onSubmit}
        onClick={e => e.stopPropagation()}
        className="bg-paper-2 rounded-lg shadow-xl max-w-md w-full p-5 space-y-4"
      >
        <header>
          <h2 className="text-lg font-semibold text-ink">Reset password</h2>
          <p className="text-sm text-ink-2 mt-1">
            Set a new temporary password for <strong>{target.email}</strong>.
            They'll be signed out of every device and need to log in with this password.
          </p>
        </header>

        <div className="space-y-1">
          <label htmlFor="rp-pw" className="text-sm font-medium text-ink-2">New password</label>
          <input
            id="rp-pw"
            type="text"
            autoComplete="off"
            required
            minLength={8}
            value={pw}
            onChange={e => setPw(e.target.value)}
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm font-mono focus:outline-none ${
              tooShort ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
            placeholder="at least 8 chars"
          />
          <PasswordStrength password={pw} />
          <p className="text-xs text-muted">
            Showing in plaintext so you can share it. Make it long + memorable;
            tell the user to change it on first login.
          </p>
        </div>

        <div className="space-y-1">
          <label htmlFor="rp-conf" className="text-sm font-medium text-ink-2">Confirm</label>
          <input
            id="rp-conf"
            type="text"
            autoComplete="off"
            required
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm font-mono focus:outline-none ${
              mismatch ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
          />
          {mismatch && <p className="text-xs text-rust">Doesn't match.</p>}
        </div>

        {copied && (
          <p className="text-xs text-moss">Copied to clipboard. Share it out-of-band.</p>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-paper-2 border border-rule text-ink-2 rounded text-sm hover:bg-paper"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={disabled}
            className="px-4 py-2 bg-rust text-white rounded text-sm font-medium hover:brightness-90 disabled:opacity-50"
          >
            {busy ? 'Resetting…' : 'Reset + log them out'}
          </button>
        </div>
      </form>
    </div>
  );
}

function RoleBadge({ role }: { role: UserRole }) {
  return role === 'admin' ? (
    <span className="text-[10px] uppercase tracking-wide bg-rule text-ink px-1.5 py-0.5 rounded font-semibold">
      admin
    </span>
  ) : null;
}

function StatusBadge({ status }: { status: UserStatus }) {
  const map: Record<UserStatus, string> = {
    active: 'bg-moss/10 text-moss',
    pending: 'bg-gold/10 text-gold-dark',
    suspended: 'bg-rust/10 text-rust',
  };
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-semibold ${map[status]}`}>
      {status}
    </span>
  );
}

// ---------- audit log tab ----------

const PAGE_SIZE = 50;

function AuditTab() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [eventTypes, setEventTypes] = useState<AuditEventType[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [eventTypeFilter, setEventTypeFilter] = useState<'' | AuditEventType>('');
  const [actorFilter, setActorFilter] = useState('');
  const [targetFilter, setTargetFilter] = useState('');
  const [sinceFilter, setSinceFilter] = useState('');
  const [untilFilter, setUntilFilter] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // load event type catalog once for the dropdown
  useEffect(() => {
    listAuditEventTypes()
      .then(r => setEventTypes(r.event_types))
      .catch(() => {});      // non-fatal — dropdown just stays empty
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listAuditEvents({
        event_type: eventTypeFilter || undefined,
        actor: actorFilter.trim() || undefined,
        target_id: targetFilter.trim() || undefined,
        since: sinceFilter ? `${sinceFilter}T00:00:00` : undefined,
        until: untilFilter ? `${untilFilter}T23:59:59` : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setEvents(r.events);
      setTotal(r.total);
    } catch (e: any) {
      setError(e?.message || 'Failed to load audit log');
    } finally {
      setLoading(false);
    }
  }, [eventTypeFilter, actorFilter, targetFilter, sinceFilter, untilFilter, page]);

  useEffect(() => { refresh(); }, [refresh]);

  // reset to page 0 whenever filters change so we don't get stranded
  // on page 5 of a much-shorter filtered result set
  useEffect(() => { setPage(0); }, [eventTypeFilter, actorFilter, targetFilter, sinceFilter, untilFilter]);

  function clearFilters() {
    setEventTypeFilter('');
    setActorFilter('');
    setTargetFilter('');
    setSinceFilter('');
    setUntilFilter('');
  }

  const maxPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return (
    <section className="space-y-4">
      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}

      {/* filters */}
      <div className="bg-paper-2 border border-rule rounded-lg p-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs text-muted block">Event</label>
            <select
              value={eventTypeFilter}
              onChange={e => setEventTypeFilter(e.target.value as '' | AuditEventType)}
              className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1"
            >
              <option value="">All events</option>
              {eventTypes.map(t => (
                <option key={t} value={t}>{eventLabel(t)}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted block">Actor</label>
            <input
              type="text"
              value={actorFilter}
              onChange={e => setActorFilter(e.target.value)}
              placeholder="email or handle"
              className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1 w-48"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted block">Target</label>
            <input
              type="text"
              value={targetFilter}
              onChange={e => setTargetFilter(e.target.value)}
              placeholder="user_id or invite code"
              className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1 w-48"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted block">Since</label>
            <input
              type="date"
              value={sinceFilter}
              onChange={e => setSinceFilter(e.target.value)}
              className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted block">Until</label>
            <input
              type="date"
              value={untilFilter}
              onChange={e => setUntilFilter(e.target.value)}
              className="bg-paper text-ink text-sm border border-rule rounded px-2 py-1"
            />
          </div>
          <button
            type="button"
            onClick={clearFilters}
            className="text-xs text-muted hover:text-ink-2 hover:underline px-2 py-1"
          >
            Clear
          </button>
          <span className="text-xs text-muted ml-auto">
            {total.toLocaleString()} event{total === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      {/* table */}
      {loading ? (
        <div className="text-muted">Loading…</div>
      ) : events.length === 0 ? (
        <div className="text-sm text-muted italic">No events match.</div>
      ) : (
        <ul className="space-y-2">
          {events.map(ev => {
            const isExpanded = expandedId === ev.id;
            return (
              <li
                key={ev.id}
                className="bg-paper-2 border border-rule rounded-lg p-3 space-y-2"
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : ev.id)}
                  className="w-full flex items-start justify-between gap-3 text-left"
                >
                  <div className="min-w-0 flex-grow">
                    <div className="flex items-center gap-2 flex-wrap">
                      <EventBadge type={ev.event_type} />
                      <span className="text-sm text-ink-2">
                        <strong>{ev.actor_user_id_string}</strong>{' '}
                        <span className="text-muted">{eventVerb(ev.event_type)}</span>{' '}
                        <strong className="font-mono text-xs">{ev.target_label || ev.target_id || '—'}</strong>
                      </span>
                    </div>
                    <div className="text-xs text-muted mt-0.5">
                      {new Date(ev.created_at).toLocaleString()} · #{ev.id}
                    </div>
                  </div>
                  <span className="text-xs text-muted shrink-0">
                    {isExpanded ? '▾' : '▸'}
                  </span>
                </button>

                {isExpanded && (
                  <div className="border-t border-rule pt-2">
                    <pre className="text-xs bg-paper border border-rule rounded p-2 overflow-x-auto font-mono">
{JSON.stringify(ev.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {/* pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between gap-3 pt-2">
          <button
            type="button"
            disabled={page <= 0}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            className="text-sm px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded hover:bg-paper disabled:opacity-40"
          >
            ← Newer
          </button>
          <span className="text-xs text-muted">
            Page {page + 1} of {maxPage + 1}
          </span>
          <button
            type="button"
            disabled={page >= maxPage}
            onClick={() => setPage(p => Math.min(maxPage, p + 1))}
            className="text-sm px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded hover:bg-paper disabled:opacity-40"
          >
            Older →
          </button>
        </div>
      )}
    </section>
  );
}

const EVENT_LABELS: Record<AuditEventType, string> = {
  'user.approve': 'Approve user',
  'user.reject': 'Reject user',
  'user.role_change': 'Change role',
  'user.suspend': 'Suspend',
  'user.reactivate': 'Reactivate',
  'invite.create': 'Create invite',
  'invite.revoke': 'Revoke invite',
  'cache.bust': 'Bust cache',
};

const EVENT_VERBS: Record<AuditEventType, string> = {
  'user.approve': 'approved',
  'user.reject': 'rejected',
  'user.role_change': 'changed role of',
  'user.suspend': 'suspended',
  'user.reactivate': 'reactivated',
  'invite.create': 'created invite',
  'invite.revoke': 'revoked invite',
  'cache.bust': 'busted cache for',
};

const EVENT_STYLES: Record<AuditEventType, string> = {
  'user.approve': 'bg-moss/10 text-moss',
  'user.reject': 'bg-rust/10 text-rust',
  'user.role_change': 'bg-gold/10 text-gold-dark',
  'user.suspend': 'bg-rust/10 text-rust',
  'user.reactivate': 'bg-moss/10 text-moss',
  'invite.create': 'bg-sky-100 text-sky-800',
  'invite.revoke': 'bg-rule text-ink-2',
  'cache.bust': 'bg-gold/10 text-gold-dark',
};

function eventLabel(type: AuditEventType): string {
  return EVENT_LABELS[type] ?? type;
}

function eventVerb(type: AuditEventType): string {
  return EVENT_VERBS[type] ?? type;
}

function EventBadge({ type }: { type: AuditEventType }) {
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-semibold ${EVENT_STYLES[type] ?? 'bg-paper-3 text-ink-2'}`}>
      {eventLabel(type)}
    </span>
  );
}

// ---------- cache tab (ad5, per-user) ----------
//
// Search-then-bust: this reuses the same account list the Users tab
// already fetches rather than adding a new lookup endpoint. Only clears
// the target user's own daily_content_cache rows — see FUTURE_FEATURES.md
// Phase 6 for the planned multi-select + global-clear follow-up.

function CacheTab() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        setAccounts(await listAccounts());
      } catch (e: any) {
        setError(e?.message || 'Failed to load users');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return accounts;
    return accounts.filter(
      a => a.email.toLowerCase().includes(q) || a.user_id.toLowerCase().includes(q),
    );
  }, [accounts, query]);

  async function onBust(a: AccountSummary) {
    if (!confirm(`Clear all cached daily content for ${a.email}? They'll get freshly generated content next time.`)) return;
    setBusyId(a.user_id);
    setError(null);
    setNotice(null);
    try {
      const r = await bustUserCache(a.user_id);
      setNotice(
        r.rows_deleted > 0
          ? `Cleared ${r.rows_deleted} cached row(s) for ${a.email}.`
          : `${a.email} had no cached content to clear.`,
      );
    } catch (e: any) {
      setError(e?.message || 'Cache bust failed');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-4">
      <p className="text-sm text-ink-2">
        Force a user's daily content to regenerate from scratch — for "my content looks
        stuck/wrong" support tickets. Safe to do any time; it's disposable cache, not source data.
      </p>

      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}
      {notice && (
        <div className="bg-sky-50 border border-sky-200 text-sky-800 rounded px-3 py-2 text-sm">{notice}</div>
      )}

      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search by email or handle…"
        className="bg-paper text-ink w-full max-w-sm px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
      />

      {loading ? (
        <div className="text-muted">Loading users…</div>
      ) : filtered.length === 0 ? (
        <div className="text-sm text-muted italic">No users match.</div>
      ) : (
        <ul className="space-y-2">
          {filtered.map(a => (
            <li
              key={a.id}
              className="bg-paper-2 border border-rule rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap"
            >
              <div className="min-w-0">
                <div className="font-medium text-ink truncate">{a.email}</div>
                <div className="text-xs text-muted truncate">
                  user_id: <code>{a.user_id}</code>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onBust(a)}
                disabled={busyId !== null}
                className="px-3 py-1.5 bg-paper-2 border border-gold/30 text-gold-dark rounded text-xs hover:bg-gold/5 disabled:opacity-50 shrink-0"
              >
                {busyId === a.user_id ? 'Clearing…' : 'Bust cache'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------- stats tab (ad5) ----------
//
// No charting library is installed anywhere in this project (checked
// package.json — no recharts/chart.js/d3), so the visualizations here are
// hand-rolled with plain CSS bars, matching the existing PasswordStrength
// component's approach rather than pulling in a new dependency for what's
// otherwise a handful of bar charts and ranked lists.

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-paper-2 border border-rule rounded-lg p-4">
      <div className="text-2xl font-bold text-ink">{value}</div>
      <div className="text-xs text-muted mt-1">{label}</div>
    </div>
  );
}

/** Horizontal bar, width proportional to value/max. */
function BarRow({
  label, value, max, displayValue, barClassName = 'bg-gold-dark',
}: {
  label: string;
  value: number;
  max: number;
  displayValue?: string;
  barClassName?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink-2 truncate pr-2">{label}</span>
        <span className="text-muted shrink-0">{displayValue ?? value}</span>
      </div>
      <div className="h-2 w-full bg-paper-3 rounded overflow-hidden">
        <div className={`h-full rounded ${barClassName}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Small day-by-day bar strip for a trend series — a sparkline without a charting lib. */
function TrendBars({
  points, valueKey, labelSuffix = '',
}: {
  points: Record<string, any>[];
  valueKey: string;
  labelSuffix?: string;
}) {
  if (points.length === 0) {
    return <div className="text-sm text-muted italic">No activity in this window.</div>;
  }
  const max = Math.max(...points.map(p => Number(p[valueKey]) || 0), 1);
  return (
    <div className="flex items-end gap-0.5 h-16">
      {points.map((p, i) => {
        const v = Number(p[valueKey]) || 0;
        const heightPct = Math.max(4, (v / max) * 100);
        return (
          <div
            key={i}
            title={`${p.date}: ${v}${labelSuffix}`}
            className="flex-1 bg-ink-2 hover:bg-muted rounded-t min-w-[2px]"
            style={{ height: `${heightPct}%` }}
          />
        );
      })}
    </div>
  );
}

function accuracyColor(accuracy: number): string {
  if (accuracy >= 80) return 'bg-moss';
  if (accuracy >= 60) return 'bg-gold';
  return 'bg-rust';
}

function StatsTab() {
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [quiz, setQuiz] = useState<QuizPerformanceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [ov, qp] = await Promise.all([getStatsOverview(), getQuizPerformanceStats()]);
        setOverview(ov);
        setQuiz(qp);
      } catch (e: any) {
        setError(e?.message || 'Failed to load stats');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="text-muted">Loading stats…</div>;
  if (error) {
    return <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>;
  }
  if (!overview || !quiz) return null;

  const scoreBucketMax = Math.max(...Object.values(quiz.score_distribution), 1);

  return (
    <div className="space-y-8">
      {/* ---- usage overview ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Usage overview</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Active users" value={overview.users.active} />
          <StatCard label="Pending approval" value={overview.users.pending} />
          <StatCard label="Suspended" value={overview.users.suspended} />
          <StatCard label="Admins" value={overview.users.admins} />
          <StatCard label="Active topics" value={`${overview.content.topics_active} / ${overview.content.topics_total}`} />
          <StatCard label="Papers seen" value={overview.content.papers_seen} />
          <StatCard label="Papers archived" value={overview.content.papers_archived} />
          <StatCard label="Quizzes taken" value={overview.content.quizzes_taken} />
        </div>
        <div className="bg-paper-2 border border-rule rounded-lg p-4">
          <div className="text-xs text-muted mb-2">Signups, last 30 days</div>
          <TrendBars points={overview.signup_trend} valueKey="signups" labelSuffix=" signup(s)" />
        </div>
      </section>

      {/* ---- quiz performance ---- */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Quiz performance</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Quizzes taken" value={quiz.total_quizzes} />
          <StatCard label="Questions answered" value={quiz.total_questions_answered} />
          <StatCard label="Overall accuracy" value={`${quiz.overall_accuracy}%`} />
          <StatCard label="Avg / median score" value={`${quiz.average_score}% / ${quiz.median_score}%`} />
        </div>

        <div className="bg-paper-2 border border-rule rounded-lg p-4 space-y-3">
          <div className="text-xs text-muted">Score distribution (by quiz)</div>
          <div className="space-y-2">
            <BarRow label="0–59%" value={quiz.score_distribution['0-59']} max={scoreBucketMax} barClassName="bg-rust" />
            <BarRow label="60–79%" value={quiz.score_distribution['60-79']} max={scoreBucketMax} barClassName="bg-gold" />
            <BarRow label="80–100%" value={quiz.score_distribution['80-100']} max={scoreBucketMax} barClassName="bg-moss" />
          </div>
        </div>

        <div className="bg-paper-2 border border-rule rounded-lg p-4">
          <div className="text-xs text-muted mb-2">Average score, last 30 days</div>
          <TrendBars points={quiz.score_trend} valueKey="avg_percentage" labelSuffix="% avg" />
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <div className="bg-paper-2 border border-rule rounded-lg p-4 space-y-3">
            <div className="text-xs text-muted">
              By topic — worst first ({quiz.by_topic.length} topic{quiz.by_topic.length === 1 ? '' : 's'})
            </div>
            {quiz.by_topic.length === 0 ? (
              <div className="text-sm text-muted italic">No quiz data yet.</div>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {quiz.by_topic.map(t => (
                  <BarRow
                    key={t.topic_id}
                    label={t.topic_name}
                    value={t.accuracy}
                    max={100}
                    displayValue={`${t.accuracy}% (${t.correct}/${t.attempts})`}
                    barClassName={accuracyColor(t.accuracy)}
                  />
                ))}
              </div>
            )}
          </div>

          <div className="bg-paper-2 border border-rule rounded-lg p-4 space-y-3">
            <div className="text-xs text-muted">By difficulty</div>
            {quiz.by_difficulty.length === 0 ? (
              <div className="text-sm text-muted italic">No quiz data yet.</div>
            ) : (
              <div className="space-y-2">
                {quiz.by_difficulty.map(d => (
                  <BarRow
                    key={d.difficulty}
                    label={d.difficulty}
                    value={d.accuracy}
                    max={100}
                    displayValue={`${d.accuracy}% (${d.correct}/${d.attempts})`}
                    barClassName={accuracyColor(d.accuracy)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <Leaderboard
            title="Most active"
            entries={quiz.top_by_volume}
            metric={e => `${e.quizzes_taken} quiz${e.quizzes_taken === 1 ? '' : 'zes'}`}
          />
          <Leaderboard
            title={`Highest accuracy (min. ${quiz.accuracy_leaderboard_min_questions} questions answered)`}
            entries={quiz.top_by_accuracy}
            metric={e => `${e.accuracy}%`}
          />
        </div>
      </section>
    </div>
  );
}

function Leaderboard({
  title, entries, metric,
}: {
  title: string;
  entries: { user_id: string; email: string; quizzes_taken: number; accuracy: number }[];
  metric: (e: { user_id: string; email: string; quizzes_taken: number; accuracy: number }) => string;
}) {
  return (
    <div className="bg-paper-2 border border-rule rounded-lg p-4 space-y-2">
      <div className="text-xs text-muted">{title}</div>
      {entries.length === 0 ? (
        <div className="text-sm text-muted italic">Not enough data yet.</div>
      ) : (
        <ol className="space-y-1.5">
          {entries.map((e, i) => (
            <li key={e.user_id} className="flex items-center justify-between text-sm gap-2">
              <span className="flex items-center gap-2 min-w-0">
                <span className="text-xs text-muted w-4 shrink-0">{i + 1}</span>
                <span className="truncate">{e.email}</span>
              </span>
              <span className="text-muted shrink-0">{metric(e)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------- topics tab (ad4) ----------
//
// The backend half of this (POST /topics/import-yaml, POST /topics/export-yaml,
// GET /topics?include_orphaned=) has existed for a while — this tab is just
// the missing admin UI wired onto it. Deeper editing of an individual topic
// still happens on its existing /topics/[id]/edit page; this tab is for the
// admin-specific ops actions (sync from disk, dump to disk, spot orphans).

function TopicsTab() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [orphanedOnly, setOrphanedOnly] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listTopics({ includeOrphaned: true });
      setTopics(rows);
    } catch (e: any) {
      setError(e?.message || 'Failed to load topics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function onImport() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await importTopicsFromYaml();
      setNotice(
        `Synced from config/topics/*.yaml: ${r.inserted} inserted, ${r.updated} updated`
        + (r.marked_orphaned ? `, ${r.marked_orphaned} marked orphaned` : '') + '.',
      );
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Import failed');
    } finally {
      setBusy(false);
    }
  }

  async function onExport() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await exportTopicsToYaml();
      setNotice(`Exported ${r.exported} topic(s) to ${r.directory}.`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Export failed');
    } finally {
      setBusy(false);
    }
  }

  const orphanedCount = topics.filter(t => !t.source_yaml_present).length;
  const visible = orphanedOnly ? topics.filter(t => !t.source_yaml_present) : topics;

  return (
    <section className="space-y-4">
      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">{error}</div>
      )}
      {notice && (
        <div className="bg-sky-50 border border-sky-200 text-sky-800 rounded px-3 py-2 text-sm">{notice}</div>
      )}

      <div className="bg-paper-2 border border-rule rounded-lg p-4 flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Sync with config/topics/*.yaml</h2>
          <p className="text-xs text-muted mt-0.5">
            Import re-reads the YAML files on disk into the database. Export writes the current
            database state back out to YAML — do this before committing any UI-made topic changes.
          </p>
        </div>
        <div className="flex gap-2 ml-auto shrink-0">
          <button
            type="button"
            onClick={onImport}
            disabled={busy}
            className="px-3 py-1.5 bg-paper-2 border border-rule text-ink-2 rounded text-sm hover:bg-paper disabled:opacity-50"
          >
            {busy ? 'Working…' : 'Import from YAML'}
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={busy}
            className="px-3 py-1.5 bg-gold-dark text-white rounded text-sm font-medium hover:bg-[#734f14] disabled:opacity-50"
          >
            {busy ? 'Working…' : 'Export to YAML'}
          </button>
        </div>
      </div>

      <div className="bg-paper-2 border border-rule rounded-lg p-3 flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={orphanedOnly}
            onChange={e => setOrphanedOnly(e.target.checked)}
          />
          Orphaned only
        </label>
        <span className="text-xs text-muted ml-auto">
          {topics.length} topic(s) · {orphanedCount} orphaned
        </span>
      </div>

      {loading ? (
        <div className="text-muted">Loading topics…</div>
      ) : visible.length === 0 ? (
        <div className="text-sm text-muted italic">
          {orphanedOnly ? 'No orphaned topics.' : 'No topics found.'}
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map(t => (
            <li
              key={t.id}
              className="bg-paper-2 border border-rule rounded-lg p-3 flex items-center justify-between gap-3 flex-wrap"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <Link href={`/topics/${encodeURIComponent(t.id)}/edit`} className="font-medium text-ink hover:underline truncate">
                    {t.name}
                  </Link>
                  {!t.active && (
                    <span className="text-[10px] uppercase tracking-wide bg-rule text-ink-2 px-1.5 py-0.5 rounded font-semibold">
                      inactive
                    </span>
                  )}
                  {!t.source_yaml_present && (
                    <span className="text-[10px] uppercase tracking-wide bg-gold/10 text-gold-dark px-1.5 py-0.5 rounded font-semibold">
                      orphaned
                    </span>
                  )}
                  {t.owner_user_id === null ? (
                    <span className="text-[10px] uppercase tracking-wide bg-paper-3 text-ink-2 px-1.5 py-0.5 rounded font-semibold">
                      system
                    </span>
                  ) : (
                    <span className="text-[10px] uppercase tracking-wide bg-gold/10 text-gold-dark px-1.5 py-0.5 rounded font-semibold">
                      user-owned
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted truncate">
                  <code>{t.id}</code> · {t.stream} · weight {t.weight} · {t.quiz_difficulty}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
