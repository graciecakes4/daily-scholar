'use client';

/**
 * /reset-password — self-serve password reset, step 2 (li3b).
 *
 * Reached via the redirect from /forgot-password with `?token=...` — a
 * single-use token minted by POST /auth/forgot-password after it
 * verified the email+username pairing. Consuming it here
 * (POST /auth/reset-password) sets the new password and revokes every
 * existing session for the account, then sends the user to /login.
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { confirmPasswordReset } from '@/lib/api';
import { AuthShell, Field } from '@/components/AuthShell';
import PasswordStrength from '@/components/PasswordStrength';

function ResetPasswordInner() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const passwordTooShort = password.length > 0 && password.length < 8;
  const passwordMismatch = confirm.length > 0 && password !== confirm;
  const disabled = submitting || !token || password.length < 8 || password !== confirm;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
      setTimeout(() => router.push('/login'), 1500);
    } catch (err: any) {
      setError(err?.message || 'Could not reset your password.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthShell title="Reset your password">
        <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">
          This link is missing its reset token. Start over from{' '}
          <Link href="/forgot-password" className="underline">
            forgot password
          </Link>
          .
        </div>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell title="Password updated">
        <p className="text-sm text-ink-2">
          You're all set — every other device has been signed out. Redirecting you to log in…
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Reset your password">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="New password" htmlFor="rp-password" hint="At least 8 characters.">
          <input
            id="rp-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={e => setPassword(e.target.value)}
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              passwordTooShort ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
          />
          <PasswordStrength password={password} />
        </Field>

        <Field label="Confirm new password" htmlFor="rp-confirm">
          <input
            id="rp-confirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              passwordMismatch ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
          />
          {passwordMismatch && <p className="text-xs text-rust">Passwords don't match.</p>}
        </Field>

        {error && (
          <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={disabled}
          className="w-full px-4 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14] disabled:opacity-50"
        >
          {submitting ? 'Resetting…' : 'Reset password'}
        </button>
      </form>
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<AuthShell title="Reset your password">Loading…</AuthShell>}>
      <ResetPasswordInner />
    </Suspense>
  );
}
