'use client';

/**
 * /account/suspended — placeholder shown to users whose accounts an
 * admin has suspended. The login endpoint 403s suspended users
 * directly, so reaching this page generally means the suspension
 * happened mid-session and the cookie was rejected on a subsequent
 * request.
 */

import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

export default function SuspendedPage() {
  const router = useRouter();
  const { logout } = useAuth();

  async function onLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <div className="bg-paper-2 border border-rust/25 rounded-lg p-6 shadow-sm space-y-4 text-center">
        <div className="text-4xl">🚫</div>
        <h1 className="font-serif text-2xl font-bold text-ink">Account suspended</h1>
        <p className="text-sm text-ink-2">
          Your Daily Scholar account has been suspended. Contact the administrator
          if you believe this was a mistake.
        </p>
        <button
          onClick={onLogout}
          className="px-4 py-2 bg-gold-dark text-white rounded text-sm font-medium hover:bg-[#734f14]"
        >
          Log out
        </button>
      </div>
    </div>
  );
}
