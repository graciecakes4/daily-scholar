'use client';

/**
 * /settings/account/username — change username.
 *
 * Requires the current password since the handle is part of the user's
 * public identity (we don't want a stolen cookie alone to rotate it).
 * Changing it re-keys every reference across the user's data in one
 * transaction; the login email stays the same.
 */

import { useMemo, useState } from 'react';
import { changeMyUsername } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

// must mirror backend/services/auth_security.py:USER_ID_REGEX
const USER_ID_REGEX = /^[a-z0-9._-]{3,30}$/;

function validateUsernameClient(handle: string): string | null {
  if (!handle) return 'pick a username';
  const norm = handle.trim().toLowerCase();
  if (norm.startsWith('__')) return "can't start with '__' (reserved)";
  if (!USER_ID_REGEX.test(norm)) return '3–30 chars, lowercase letters/digits/_-. only';
  return null;
}

export default function UsernamePage() {
  const { user, loading, refresh } = useAuth();

  if (loading) return <div className="text-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto mt-12 max-w-md rounded-lg border border-rule bg-paper-2 p-6 text-center">
        <p className="text-sm text-ink-2">You need to log in to manage your account.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif text-3xl font-semibold text-ink">Username</h1>
        <p className="mt-1 text-ink-2">
          Your public handle — what other users see when they discover topics you've shared.
        </p>
      </header>

      <ChangeUsernameCard currentUserId={user.user_id} onSaved={refresh} />
    </div>
  );
}

function ChangeUsernameCard({
  currentUserId, onSaved,
}: { currentUserId: string; onSaved: () => Promise<void> }) {
  const [current, setCurrent] = useState('');
  const [handle, setHandle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleError = useMemo(() => validateUsernameClient(handle), [handle]);
  const sameAsCurrent = handle.trim().toLowerCase() === currentUserId;
  const disabled = busy || !current || !!handleError || sameAsCurrent;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await changeMyUsername(current, handle.trim().toLowerCase());
      if (r.changed) {
        const moved = Object.values(r.rows_moved || {}).reduce((a, b) => a + b, 0);
        setSuccess(`Username updated to "${r.new_user_id}". ${moved} row(s) re-keyed across your data.`);
        setCurrent('');
        setHandle('');
        await onSaved();         // refresh the auth header so the new handle shows up
      } else {
        setSuccess('Username is unchanged.');
      }
    } catch (e: any) {
      setError(e?.message || 'Username change failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-rule bg-paper-2 p-5">
      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>
      )}
      {success && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{success}</div>
      )}

      <p className="text-sm text-ink-2">
        Current handle: <code>{currentUserId}</code>.
      </p>

      <Field
        label="New username"
        htmlFor="cu-handle"
        hint="3–30 chars, lowercase letters/digits/_-."
      >
        <input
          id="cu-handle"
          type="text"
          autoComplete="username"
          value={handle}
          onChange={e => setHandle(e.target.value.toLowerCase())}
          className={`w-full rounded border px-3 py-2 font-mono text-sm focus:outline-none ${
            handleError && handle ? 'border-rose-400 focus:border-rose-600' : 'border-rule focus:border-ink'
          }`}
        />
        {handle && handleError && <p className="text-xs text-rose-700">{handleError}</p>}
        {handle && !handleError && sameAsCurrent && (
          <p className="text-xs text-muted">That's already your handle.</p>
        )}
      </Field>

      <Field label="Current password" htmlFor="cu-current" hint="Required to confirm it's really you.">
        <input
          id="cu-current"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={e => setCurrent(e.target.value)}
          className="w-full rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:border-ink"
        />
      </Field>

      <p className="text-xs text-muted">
        Changing your username updates every reference to it across your data (papers, reviews,
        quizzes, subscriptions, etc.) in one transaction. Your login email stays the same.
      </p>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={disabled}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink-2 disabled:opacity-50"
        >
          {busy ? 'Updating…' : 'Update username'}
        </button>
      </div>
    </form>
  );
}

function Field({
  label, htmlFor, hint, children,
}: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <label htmlFor={htmlFor} className="text-sm font-medium text-ink-2">{label}</label>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
