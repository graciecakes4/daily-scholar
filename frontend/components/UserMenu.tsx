'use client';

/**
 * UserMenu — top-right corner widget showing the logged-in user (or
 * a Login button when logged out). Used by the layout's nav bar.
 *
 * Calls /auth/me on mount via useAuth(). Suppresses itself on the
 * auth routes (/login, /signup, /account/*) so the auth pages aren't
 * cluttered with a "log in" button that fights the form.
 */

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

const HIDE_PATH_PREFIXES = ['/login', '/signup', '/account/'];

export default function UserMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();

  if (pathname && HIDE_PATH_PREFIXES.some(p => pathname.startsWith(p))) {
    return null;
  }

  // skeleton while /auth/me is in flight — keeps the nav width stable
  if (loading) {
    return <div className="h-8 w-24 bg-slate-100 rounded animate-pulse" />;
  }

  if (!user) {
    return (
      <Link
        href="/login"
        className="ml-2 px-3 py-1.5 text-sm font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors"
      >
        Log in
      </Link>
    );
  }

  async function onLogout() {
    await logout();
    router.push('/login');
  }

  // display the username (handle) when it differs from the email; fall back
  // to email so it's never ambiguous who's signed in
  const handle = user.user_id !== user.email ? user.user_id : user.email;

  return (
    <div className="ml-2 flex items-center gap-2">
      <span className="hidden sm:inline text-sm text-slate-600 truncate max-w-[180px]" title={user.email}>
        {handle}
      </span>
      {user.role === 'admin' && (
        <span className="text-[10px] uppercase tracking-wide bg-slate-200 text-slate-700 px-1.5 py-0.5 rounded font-semibold">
          admin
        </span>
      )}
      <button
        type="button"
        onClick={onLogout}
        className="px-3 py-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors"
      >
        Log out
      </button>
    </div>
  );
}
