'use client';

/**
 * AuthBoundary — sticky banner that appears whenever fetchAPI dispatches a
 * 401 event. Mounted once at the layout root so any page-level API call can
 * trigger it without prop-drilling state.
 *
 * Why a global event rather than a React context: most API calls happen
 * inside SWR-style hooks or page-level useEffects, not React components.
 * A window event lets the API layer (which is plain TS) trigger the UI
 * without coupling to React internals.
 *
 * Solo mode never hits this code path — get_current_user_id always returns
 * an identity. It's strictly for the CF Access multi-user case where the
 * user's session expires mid-app.
 */

import { useEffect, useState } from 'react';
import { AUTH_ERROR_EVENT } from '@/lib/api';

interface AuthErrorDetail {
  status: number;
  message: string;
}

export default function AuthBoundary() {
  const [error, setError] = useState<AuthErrorDetail | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<AuthErrorDetail>;
      setError(ce.detail);
    };
    window.addEventListener(AUTH_ERROR_EVENT, handler);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, handler);
  }, []);

  if (!error) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="fixed top-16 left-0 right-0 z-50 mx-auto max-w-2xl px-4"
    >
      <div className="bg-amber-50 border border-amber-300 rounded-lg shadow-lg p-4 flex items-start gap-3">
        <svg
          className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-amber-900 text-sm">
            Authentication required
          </h3>
          <p className="text-amber-800 text-sm mt-1">
            Your Cloudflare Access session has expired or wasn't established.
            Reload this page to sign in again. ({error.message})
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-md transition-colors"
            >
              Reload
            </button>
            <button
              type="button"
              onClick={() => setError(null)}
              className="px-3 py-1.5 bg-white hover:bg-amber-100 text-amber-900 text-sm font-medium rounded-md border border-amber-300 transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
