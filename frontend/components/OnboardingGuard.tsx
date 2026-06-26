'use client';

/**
 * OnboardingGuard — bounces logged-in unonboarded users to /onboarding.
 *
 * Mounts once in the layout (alongside AuthBoundary). Skips the redirect
 * on auth + onboarding routes themselves so we don't loop. AuthBoundary
 * handles the not-logged-in case; this guard handles the
 * logged-in-but-pre-wizard case.
 */

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';

const SKIP_PREFIXES = ['/onboarding', '/login', '/signup', '/account/'];

export default function OnboardingGuard() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!user) return;                       // AuthBoundary will route to /login
    if (user.onboarded) return;              // nothing to do
    if (!pathname) return;
    if (SKIP_PREFIXES.some(p => pathname.startsWith(p))) return;
    router.push('/onboarding');
  }, [loading, user, pathname, router]);

  return null;
}
