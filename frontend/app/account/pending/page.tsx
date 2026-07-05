'use client';

/**
 * /account/pending — placeholder shown to users whose account is
 * created but not yet admin-approved. All app endpoints will 403 them
 * via get_current_user_id; this page is the only thing that renders
 * cleanly for them after login.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

export default function PendingPage() {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  async function onLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <div className="bg-paper-2 border border-rule rounded-lg p-6 shadow-sm space-y-4 text-center">
        <div className="text-4xl">⏳</div>
        <h1 className="text-2xl font-bold text-ink">Awaiting approval</h1>
        <p className="text-sm text-ink-2">
          Your account has been created and is waiting for an administrator to approve it.
          You'll be able to use Daily Scholar as soon as that happens — usually within a day.
        </p>
        {!loading && user && (
          <p className="text-xs text-muted font-mono">
            Signed in as {user.email}
          </p>
        )}
        <div className="flex gap-2 justify-center pt-2">
          <Link
            href="/"
            className="px-4 py-2 bg-gold-dark text-white rounded text-sm font-medium hover:bg-[#734f14]"
          >
            Try app again
          </Link>
          <button
            onClick={onLogout}
            className="px-4 py-2 bg-paper-2 border border-rule text-ink-2 rounded text-sm hover:bg-paper"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  );
}
