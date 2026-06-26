'use client';

/**
 * useAuth — lightweight per-component auth state hook.
 *
 * Calls GET /auth/me on mount, exposes the resulting profile (or null
 * when logged out / not yet resolved). Triggers a re-fetch on mount so
 * page navigations see fresh state.
 *
 * For app-wide concerns (redirect on 401, login/logout actions) the
 * AuthBoundary component listens to the global AUTH_ERROR_EVENT; this
 * hook is for components that need to *display* the current user
 * (e.g., a nav header showing the username + logout button).
 */

import { useCallback, useEffect, useState } from 'react';
import {
  AUTH_CHANGED_EVENT,
  getMe,
  login as apiLogin,
  logout as apiLogout,
  type AuthUser,
  type LoginBody,
} from '@/lib/api';

export interface UseAuthResult {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: (body: LoginBody) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { profile } = await getMe();
      setUser(profile);
    } catch (e: any) {
      // 401 is expected when logged out; surface other errors
      if (e?.status === 401 || e?.name === 'AuthError') {
        setUser(null);
      } else {
        setError(e?.message || 'Failed to load profile');
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // re-fetch /auth/me whenever any other useAuth() instance reports a
  // login or logout. Keeps the layout-level UserMenu in sync with form
  // submissions from the page tree below it.
  useEffect(() => {
    const handler = () => { refresh(); };
    window.addEventListener(AUTH_CHANGED_EVENT, handler);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, handler);
  }, [refresh]);

  const login = useCallback(async (body: LoginBody) => {
    const { profile } = await apiLogin(body);
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  return { user, loading, error, login, logout, refresh };
}
