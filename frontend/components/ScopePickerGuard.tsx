'use client';

/**
 * ScopePickerGuard — bounces logged-in onboarded users with no active
 * scope to /scopes/picker so the rest of the app always has a scope to
 * drive discovery / quizzes / reviews.
 *
 * Runs after OnboardingGuard: AuthBoundary handles "no user" → /login,
 * OnboardingGuard handles "no profile" → /onboarding, and this guard
 * handles "no active scope" → /scopes/picker. Each guard is a no-op
 * when its precondition isn't met, so they compose cleanly even though
 * they all mount in the same layout.
 *
 * The picker, browse, and editor routes are explicitly skipped so the
 * user can navigate around inside the scope-setup surface without
 * being yanked back to the picker every render.
 */

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getActiveScope } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

// pathnames where the picker shouldn't bounce: the picker itself, all
// scope-management surfaces, and the standard auth / onboarding routes.
const SKIP_PREFIXES = [
  '/scopes',
  '/settings/scope',
  '/onboarding',
  '/login',
  '/signup',
  '/account/',
];

export default function ScopePickerGuard() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading } = useAuth();

  // remember the last user_id we checked for, so the active-scope probe
  // refires after login/logout without firing on every nav within the
  // same session
  const [checkedFor, setCheckedFor] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      // logged out — reset so a fresh login re-probes
      if (checkedFor !== null) setCheckedFor(null);
      return;
    }
    if (!user.onboarded) return;             // OnboardingGuard handles this
    if (checkedFor === user.user_id) return; // already probed this session
    if (!pathname) return;
    if (SKIP_PREFIXES.some(p => pathname.startsWith(p))) return;

    (async () => {
      try {
        const active = await getActiveScope();
        if (active === null) {
          router.push('/scopes/picker');
        }
      } catch {
        // best-effort guard: failing the probe shouldn't trap the user
        // in a redirect loop. If /user/active-scope is unreachable, just
        // let the app render normally.
      } finally {
        setCheckedFor(user.user_id);
      }
    })();
  }, [loading, user, pathname, router, checkedFor]);

  return null;
}
