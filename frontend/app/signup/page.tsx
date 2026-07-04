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
import { AuthShell, Field } from '@/components/AuthShell';
import PasswordStrength from '@/components/PasswordStrength';

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
  const [inviteCode, setInviteCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleError = useMemo(() => validateUserIdClient(userId), [userId]);
  const passwordTooShort = password.length > 0 && password.length < 8;
  const passwordMismatch = confirm.length > 0 && password !== confirm;

  // we don't know client-side whether OPEN_SIGNUP is on, so we always show
  // the invite-code field. The backend decides whether to require it; if
  // the user leaves it blank and the server is gated, the 400 message
  // bubbles up via `error` and they can paste the code in then.
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
        invite_code: inviteCode.trim() || undefined,
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
        <Field
          label="Invite code"
          htmlFor="su-invite"
          hint="An admin should have shared one with you. Required for new accounts."
        >
          <input
            id="su-invite"
            type="text"
            autoComplete="off"
            value={inviteCode}
            onChange={e => setInviteCode(e.target.value)}
            placeholder="e.g. aB3-x7F_kLm"
            className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm font-mono focus:outline-none focus:border-ink"
          />
        </Field>

        <Field label="Email" htmlFor="su-email">
          <input
            id="su-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
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
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              handleError ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
          />
          {handleError && <p className="text-xs text-rust">{handleError}</p>}
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
            className={`bg-paper text-ink w-full px-3 py-2 border rounded text-sm focus:outline-none ${
              passwordTooShort ? 'border-rust/30 focus:border-rust/40' : 'border-rule focus:border-ink'
            }`}
          />
          <PasswordStrength password={password} />
        </Field>

        <Field label="Confirm password" htmlFor="su-confirm">
          <input
            id="su-confirm"
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

        <p className="text-xs text-muted">
          New accounts require administrator approval before you can use the app.
        </p>

        <button
          type="submit"
          disabled={disabled}
          className="w-full px-4 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14] disabled:opacity-50"
        >
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="text-sm text-ink-2 text-center mt-6">
        Already have an account?{' '}
        <Link href="/login" className="text-sky-700 hover:underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}
