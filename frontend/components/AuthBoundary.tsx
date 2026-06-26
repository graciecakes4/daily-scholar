'use client';

/**
 * AuthBoundary — global redirect-to-/login on 401.
 *
 * Listens to the `daily-scholar:auth-error` event that fetchAPI emits
 * on any 401 response. When triggered:
 *   - If the user is already on an auth/account route, do nothing
 *     (avoids redirect loops on /login itself).
 *   - Otherwise: redirect to /login?next=<current path> so the user
 *     can land back on what they were trying to do.
 *
 * Also handles the special 403 cases (account pending / suspended) by
 * routing the user to the appropriate placeholder page. The api.ts
 * layer would need to emit a different event for those — for now,
 * 401 is the only one we intercept globally; pending/suspended users
 * hit the placeholder pages via the login redirect chain.
 */

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { AUTH_ERROR_EVENT } from '@/lib/api';

// routes where a 401 should NOT trigger a redirect (we're already at the
// authentication surface; redirecting would loop)
const NO_REDIRECT_PREFIXES = ['/login', '/signup', '/account/'];

export default function AuthBoundary() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<{ status: number; message: string; redirect?: string }>;
      // 403 with a route hint (pending / suspended) wins outright — bounce
      // the user to the matching placeholder page no matter where they are.
      if (ce.detail?.redirect) {
        if (pathname !== ce.detail.redirect) {
          router.push(ce.detail.redirect);
        }
        return;
      }
      // 401 path: skip on auth routes (no loops), otherwise redirect with
      // a `?next=` so we can land them back on what they were doing.
      if (pathname && NO_REDIRECT_PREFIXES.some(p => pathname.startsWith(p))) {
        return;
      }
      const next = pathname && pathname !== '/' ? `?next=${encodeURIComponent(pathname)}` : '';
      router.push(`/login${next}`);
    };
    window.addEventListener(AUTH_ERROR_EVENT, handler);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, handler);
  }, [pathname, router]);

  return null;
}
