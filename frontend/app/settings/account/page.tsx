'use client';

/**
 * /settings/account — self-service account mutations.
 *
 * Two cards:
 *   - Change password (current + new + confirm)
 *   - Change username (current password + new handle, with live regex hint)
 *
 * Both require the user's current password — password change because
 * that's the point, username change because the handle is part of the
 * user's public identity (we don't want a stolen cookie alone to rotate
 * it). On successful password change, the server revokes every OTHER
 * session for the user; the current session stays alive via the cookie
 * token.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import {
  changeMyPassword,
  changeMyUsername,
  resetTour,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import PasswordStrength from '@/components/PasswordStrength';

// must mirror backend/services/auth_security.py:USER_ID_REGEX
const USER_ID_REGEX = /^[a-z0-9._-]{3,30}$/;

function validateUsernameClient(handle: string): string | null {
  if (!handle) return 'pick a username';
  const norm = handle.trim().toLowerCase();
  if (norm.startsWith('__')) return "can't start with '__' (reserved)";
  if (!USER_ID_REGEX.test(norm)) return '3–30 chars, lowercase letters/digits/_-. only';
  return null;
}

export default function AccountSettingsPage() {
  const { user, loading, refresh } = useAuth();

  if (loading) return <div className="text-slate-500">Loading…</div>;
  if (!user) {
    return (
      <div className="max-w-md mx-auto mt-12 bg-white border border-slate-200 rounded-lg p-6 text-center">
        <p className="text-sm text-slate-600">You need to log in to manage your account.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Account</h1>
          <p className="text-slate-600 mt-1">
            Signed in as <code className="text-sm">{user.email}</code> · handle <code className="text-sm">{user.user_id}</code>
          </p>
        </div>
        <nav className="text-sm">
          <Link href="/settings/scope" className="text-sky-700 hover:underline">← Settings</Link>
        </nav>
      </header>

      <ChangePasswordCard onSaved={refresh} />
      <ChangeUsernameCard currentUserId={user.user_id} onSaved={refresh} />
      <TourReplayCard onReset={refresh} />
    </div>
  );
}

// ---------- replay tour ----------

function TourReplayCard({ onReset }: { onReset: () => Promise<void> }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function replay() {
    setBusy(true);
    setError(null);
    try {
      // server-side: zero users.tour_version_seen so the gate re-opens
      await resetTour();
      // refresh /auth/me so the in-memory auth state matches the new
      // server value BEFORE we route — otherwise DashboardTour might
      // gate on the stale (already-seen) value and skip
      await onReset();
      router.push('/');
    } catch (e: any) {
      setError(e?.message || 'Could not reset the tour');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
        Product tour
      </h2>
      <p className="text-sm text-slate-600">
        Replay the 4-step walkthrough that ran on your first login. Useful if you skipped it
        too fast or want a refresher on where things live. Synced across every device you log in from.
      </p>
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={replay}
          disabled={busy}
          className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
        >
          {busy ? 'Resetting…' : 'Show me around again'}
        </button>
      </div>
    </section>
  );
}

// ---------- change password ----------

function ChangePasswordCard({ onSaved }: { onSaved: () => Promise<void> }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const tooShort = next.length > 0 && next.length < 8;
  const mismatch = confirm.length > 0 && next !== confirm;
  const disabled = busy || !current || next.length < 8 || next !== confirm;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await changeMyPassword(current, next);
      const revoked = r.other_sessions_revoked;
      setSuccess(
        revoked > 0
          ? `Password updated. ${revoked} other session(s) on other devices were signed out.`
          : 'Password updated.',
      );
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (e: any) {
      setError(e?.message || 'Password change failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Change password</h2>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}
      {success && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded px-3 py-2 text-sm">{success}</div>
      )}

      <Field label="Current password" htmlFor="cp-current">
        <input
          id="cp-current"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={e => setCurrent(e.target.value)}
          className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
        />
      </Field>

      <Field label="New password" htmlFor="cp-new" hint="At least 8 characters.">
        <input
          id="cp-new"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={next}
          onChange={e => setNext(e.target.value)}
          className={`w-full px-3 py-2 border rounded text-sm focus:outline-none ${
            tooShort ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
          }`}
        />
        <PasswordStrength password={next} />
      </Field>

      <Field label="Confirm new password" htmlFor="cp-confirm">
        <input
          id="cp-confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          className={`w-full px-3 py-2 border rounded text-sm focus:outline-none ${
            mismatch ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
          }`}
        />
        {mismatch && <p className="text-xs text-rose-700">Passwords don't match.</p>}
      </Field>

      <p className="text-xs text-slate-500">
        Other devices you're signed in on will be logged out. Your current device stays.
      </p>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={disabled}
          className="px-4 py-2 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? 'Updating…' : 'Update password'}
        </button>
      </div>
    </form>
  );
}

// ---------- change username ----------

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
    <form onSubmit={onSubmit} className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Change username</h2>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">{error}</div>
      )}
      {success && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded px-3 py-2 text-sm">{success}</div>
      )}

      <p className="text-sm text-slate-600">
        Your username is your public handle — it's what other users see when they discover topics you've shared.
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
          className={`w-full px-3 py-2 border rounded text-sm font-mono focus:outline-none ${
            handleError && handle ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
          }`}
        />
        {handle && handleError && <p className="text-xs text-rose-700">{handleError}</p>}
        {handle && !handleError && sameAsCurrent && (
          <p className="text-xs text-slate-500">That's already your handle.</p>
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
          className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
        />
      </Field>

      <p className="text-xs text-slate-500">
        Changing your username updates every reference to it across your data (papers, reviews,
        quizzes, subscriptions, etc.) in one transaction. Your login email stays the same.
      </p>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={disabled}
          className="px-4 py-2 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? 'Updating…' : 'Update username'}
        </button>
      </div>
    </form>
  );
}

// ---------- shared bits ----------

function Field({
  label, htmlFor, hint, children,
}: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <label htmlFor={htmlFor} className="text-sm font-medium text-slate-700">{label}</label>
        {hint && <span className="text-xs text-slate-400">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
