'use client';

/**
 * /signup — create a new account.
 *
 * In Phase A, signup is open (no invite code) so we can E2E test the
 * chain. Phase B will add an invite-code field and validation. New
 * accounts land in `pending` status until an admin approves them; the
 * page redirects to /account/pending on success.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { signup } from '@/lib/api';
import { AuthShell, Field } from '../login/page';

// must mirror backend/services/auth_security.py:USER_ID_REGEX
const USER_ID_REGEX = /^[a-z0-9._-]{3,30}$/;

function validateUserIdClient(handle: string): string | null {
  if (!handle) return null;                          // empty = use default (email)
  const normalized = handle.trim().toLowerCase();
  if (normalized.startsWith('__')) return "Can't start with '__' (reserved)";
  if (!USER_ID_REGEX.test(normalized)) {
    return '3–30 chars, lowercase letters/digits/_-. only';
  }
  return null;
}

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [userId, setUserId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleError = useMemo(() => validateUserIdClient(userId), [userId]);
  const passwordTooShort = password.length > 0 && password.length < 8;
  const passwordMismatch = confirm.length > 0 && password !== confirm;

  const disabled =
    submitting ||
    !email ||
    password.length < 8 ||
    password !== confirm ||
    !!handleError;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signup({
        email,
        password,
        user_id: userId.trim() || undefined,
      });
      router.push('/account/pending');
    } catch (err: any) {
      setError(err?.message || 'Signup failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="Create your account">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Email" htmlFor="su-email">
          <input
            id="su-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
          />
        </Field>

        <Field
          label="Username (optional)"
          htmlFor="su-userid"
          hint="3–30 chars, lowercase letters/digits/_-. Defaults to your email if left blank."
        >
          <input
            id="su-userid"
            type="text"
            autoComplete="username"
            value={userId}
            onChange={e => setUserId(e.target.value.toLowerCase())}
            placeholder="(uses your email)"
            className={`w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              handleError ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
            }`}
          />
          {handleError && <p className="text-xs text-rose-700">{handleError}</p>}
        </Field>

        <Field label="Password" htmlFor="su-password" hint="At least 8 characters.">
          <input
            id="su-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={e => setPassword(e.target.value)}
            className={`w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              passwordTooShort ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
            }`}
          />
        </Field>

        <Field label="Confirm password" htmlFor="su-confirm">
          <input
            id="su-confirm"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            className={`w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              passwordMismatch ? 'border-rose-400 focus:border-rose-600' : 'border-slate-300 focus:border-slate-900'
            }`}
          />
          {passwordMismatch && <p className="text-xs text-rose-700">Passwords don't match.</p>}
        </Field>

        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <p className="text-xs text-slate-500">
          New accounts require administrator approval before you can use the app.
        </p>

        <button
          type="submit"
          disabled={disabled}
          className="w-full px-4 py-2 bg-slate-900 text-white rounded font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="text-sm text-slate-600 text-center mt-6">
        Already have an account?{' '}
        <Link href="/login" className="text-sky-700 hover:underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}
