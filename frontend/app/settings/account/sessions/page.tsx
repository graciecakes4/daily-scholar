'use client';

/**
 * /settings/account/sessions — devices where you're signed in.
 *
 * Lists active `Session` rows (server-side login sessions), not the
 * push-subscription "devices" managed on /settings/notifications — those
 * are a deliberately separate concept (a phone can be logged in without
 * push enabled, or push-subscribed on a browser tab that later logs out).
 *
 * Each row can be revoked individually; "Log out everywhere else" revokes
 * every session but the one making the request (self-reauth pattern —
 * mirrors the session cleanup on a self-service password change).
 */

import { useEffect, useState } from 'react';
import { listSessions, revokeSession, logOutEverywhere, type SessionInfo } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

// small heuristic UA parser — good enough for a device list, not a full
// UA library. falls back gracefully on anything it doesn't recognize.
function parseUserAgent(ua: string | null): string {
  if (!ua) return 'Unknown device';

  let os = 'Unknown OS';
  if (/iPad/.test(ua)) os = 'iPad';
  else if (/iPhone|iPod/.test(ua)) os = 'iPhone';
  else if (/Android/.test(ua)) os = 'Android';
  else if (/Macintosh/.test(ua)) os = 'Mac';
  else if (/Windows/.test(ua)) os = 'Windows';
  else if (/Linux/.test(ua)) os = 'Linux';

  let browser = 'Unknown browser';
  if (/EdgiOS|Edg\//.test(ua)) browser = 'Edge';
  else if (/CriOS|Chrome\//.test(ua)) browser = 'Chrome';
  else if (/FxiOS|Firefox\//.test(ua)) browser = 'Firefox';
  else if (/Safari\//.test(ua) && !/Chrome/.test(ua)) browser = 'Safari';

  return `${browser} on ${os}`;
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'unknown';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
  const months = Math.round(days / 30);
  return `${months} mo${months === 1 ? '' : 's'} ago`;
}

export default function SessionsPage() {
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
        <h1 className="font-serif text-3xl font-semibold text-ink">Sessions</h1>
        <p className="mt-1 text-ink-2">Devices where you're currently signed in.</p>
      </header>

      <SessionsCard />
    </div>
  );
}

function SessionsCard() {
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyAll, setBusyAll] = useState(false);

  async function refresh() {
    try {
      const r = await listSessions();
      setSessions(r.sessions);
    } catch (e: any) {
      setError(e?.message || 'Failed to load sessions');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onRevoke(s: SessionInfo) {
    setBusyId(s.id);
    setError(null);
    setSuccess(null);
    try {
      const r = await revokeSession(s.id);
      setSuccess(r.revoked_current ? 'Signed this device out.' : 'Session signed out.');
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Failed to sign out that session');
    } finally {
      setBusyId(null);
    }
  }

  async function onLogOutEverywhere() {
    setBusyAll(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await logOutEverywhere();
      setSuccess(
        r.revoked > 0 ? `Signed out ${r.revoked} other session(s).` : 'No other sessions to sign out.',
      );
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Failed to sign out other sessions');
    } finally {
      setBusyAll(false);
    }
  }

  const otherCount = sessions ? sessions.filter(s => !s.is_current).length : 0;

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>
      )}
      {success && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {success}
        </div>
      )}

      <div className="rounded-lg border border-rule bg-paper-2 p-5 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <p className="text-xs text-muted max-w-[52ch]">
            Signing out a session immediately blocks that device from making further requests.
          </p>
          <button
            type="button"
            onClick={onLogOutEverywhere}
            disabled={busyAll || otherCount === 0}
            className="rounded bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-ink-2 disabled:opacity-50 flex-shrink-0"
          >
            {busyAll ? 'Signing out…' : 'Log out everywhere else'}
          </button>
        </div>

        {sessions === null ? (
          <p className="text-sm text-muted">Loading sessions…</p>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-muted">No active sessions.</p>
        ) : (
          <ul className="divide-y divide-rule">
            {sessions.map(s => (
              <li key={s.id} className="flex items-center justify-between gap-4 py-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-ink">{parseUserAgent(s.user_agent)}</span>
                    {s.is_current && (
                      <span className="text-xs font-semibold text-moss bg-moss/10 border border-moss/25 rounded-full px-2.5 py-0.5">
                        This device
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted mt-0.5">
                    {s.ip ? `${s.ip} · ` : ''}
                    {s.last_seen_at ? `Active ${relativeTime(s.last_seen_at)}` : `Signed in ${relativeTime(s.created_at)}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onRevoke(s)}
                  disabled={busyId === s.id}
                  className="text-xs font-semibold text-muted hover:text-rust disabled:opacity-50 flex-shrink-0"
                >
                  {busyId === s.id ? 'Signing out…' : s.is_current ? 'Sign out this device' : 'Sign out'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
