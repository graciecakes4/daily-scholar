'use client';

/**
 * /forgot-password — self-serve password reset, step 1 (li3b).
 *
 * Submits an email; the backend sends a reset link to that address if
 * it belongs to an active account (SMTP-configured — see
 * backend/services/email.py). The response is the exact same generic
 * message either way, so this page never tries to branch on whether
 * the email matched — doing so would defeat the point of not leaking
 * which emails have accounts.
 */

import Link from 'next/link';
import { useState } from 'react';
import { requestPasswordReset } from '@/lib/api';
import { AuthShell, Field } from '@/components/AuthShell';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err: any) {
      setError(err?.message || 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <AuthShell title="Check your email">
        <p className="text-sm text-ink-2">
          If an account exists for <span className="font-medium">{email}</span>, we've sent a
          link to reset your password. It expires in 30 minutes.
        </p>
        <p className="text-sm text-ink-2 text-center mt-6">
          <Link href="/login" className="text-sky-700 hover:underline">
            Back to log in
          </Link>
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Forgot your password?">
      <p className="text-sm text-ink-2 mb-4">
        Enter the email on your account and we'll send you a link to reset your password.
      </p>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Email" htmlFor="fp-email">
          <input
            id="fp-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
          />
        </Field>

        {error && (
          <div className="bg-rust/5 border border-rust/25 text-rust rounded px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full px-4 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14] disabled:opacity-50"
        >
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>

      <p className="text-sm text-ink-2 text-center mt-6">
        Remembered it?{' '}
        <Link href="/login" className="text-sky-700 hover:underline">
          Log in
        </Link>
      </p>
    </AuthShell>
  );
}
