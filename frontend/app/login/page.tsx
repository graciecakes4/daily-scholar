'use client';

/**
 * /login — email + password sign-in.
 *
 * On success: pending users → /account/pending, suspended will have
 * been rejected at the API layer with a 403, anything else → /.
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { AuthShell, Field } from '@/components/AuthShell';

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ?next=/some/path lets us send users back to where they tried to go
  const nextPath = params.get('next') || '/';

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const profile = await login({ email, password });
      if (profile.status === 'pending') {
        router.push('/account/pending');
      } else {
        router.push(nextPath);
      }
    } catch (err: any) {
      setError(err?.message || 'Login failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="Log in">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Email" htmlFor="login-email">
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
          />
        </Field>
        <Field label="Password" htmlFor="login-password">
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
          />
        </Field>

        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full px-4 py-2 bg-slate-900 text-white rounded font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? 'Signing in…' : 'Log in'}
        </button>
      </form>

      <p className="text-sm text-slate-600 text-center mt-6">
        Don't have an account?{' '}
        <Link href="/signup" className="text-sky-700 hover:underline">
          Sign up
        </Link>
      </p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthShell title="Log in">Loading…</AuthShell>}>
      <LoginInner />
    </Suspense>
  );
}
