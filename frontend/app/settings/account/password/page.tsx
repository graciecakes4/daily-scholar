'use client';

/**
 * /settings/account/password — change password.
 *
 * Requires the current password. On success, the server revokes every
 * OTHER session for the user; the current session stays alive via the
 * cookie token.
 */

import { useState } from 'react';
import { changeMyPassword } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import PasswordStrength from '@/components/PasswordStrength';

export default function PasswordPage() {
  const { user, loading } = useAuth();

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
        <h1 className="font-serif text-3xl font-semibold text-ink">Password</h1>
        <p className="mt-1 text-ink-2">Update your password. Other signed-in devices will be logged out.</p>
      </header>

      <ChangePasswordCard />
    </div>
  );
}

function ChangePasswordCard() {
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
    <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-rule bg-paper-2 p-5">
      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>
      )}
      {success && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{success}</div>
      )}

      <Field label="Current password" htmlFor="cp-current">
        <input
          id="cp-current"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={e => setCurrent(e.target.value)}
          className="w-full rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:border-ink"
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
          className={`w-full rounded border px-3 py-2 text-sm focus:outline-none ${
            tooShort ? 'border-rose-400 focus:border-rose-600' : 'border-rule focus:border-ink'
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
          className={`w-full rounded border px-3 py-2 text-sm focus:outline-none ${
            mismatch ? 'border-rose-400 focus:border-rose-600' : 'border-rule focus:border-ink'
          }`}
        />
        {mismatch && <p className="text-xs text-rose-700">Passwords don't match.</p>}
      </Field>

      <p className="text-xs text-muted">
        Other devices you're signed in on will be logged out. Your current device stays.
      </p>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={disabled}
          className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink-2 disabled:opacity-50"
        >
          {busy ? 'Updating…' : 'Update password'}
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
