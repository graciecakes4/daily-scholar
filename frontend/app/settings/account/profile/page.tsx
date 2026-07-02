'use client';

/**
 * /settings/account/profile — read-only identity summary.
 *
 * Password and username live on their own pages (/settings/account/password,
 * /settings/account/username) since they're separate mutations with separate
 * forms; this page is just the "who am I" landing spot Account resolves to.
 */

import { useAuth } from '@/hooks/useAuth';

export default function ProfilePage() {
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
        <h1 className="font-serif text-3xl font-semibold text-ink">Profile</h1>
        <p className="mt-1 text-ink-2">Your identity across Daily Scholar.</p>
      </header>

      <section className="rounded-lg border border-rule bg-paper-2 p-5 space-y-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Email</h2>
          <p className="mt-1 text-sm text-ink">{user.email}</p>
        </div>
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Username</h2>
          <p className="mt-1 text-sm text-ink">
            <code className="font-mono">{user.user_id}</code>
          </p>
          <p className="mt-1 text-xs text-muted">
            Your public handle — visible to others when you share topics.
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Role</h2>
          <p className="mt-1 text-sm text-ink">{user.role === 'admin' ? 'Scholar · admin' : 'Scholar'}</p>
        </div>
      </section>
    </div>
  );
}
