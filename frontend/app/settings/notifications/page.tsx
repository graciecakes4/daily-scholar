'use client';

/**
 * Notifications settings — one card per notification type from the
 * server-side registry. Each card has an enable toggle, a simple
 * time picker (extended with a day-of-week selector for weekly), a
 * Preview button (renders the payload without sending), and a Test
 * button (fires through the real push pipeline).
 *
 * The cron expression is the source of truth on disk; the UI
 * helpers below parse/format the subset of cron we actually expose
 * ("M H * * *" for daily, "M H * * DOW" for weekly). If a power user
 * has hand-edited the JSON to something exotic, the picker hides
 * itself and we show the raw cron string in a read-only input so we
 * never silently overwrite it.
 */

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  getNotificationSettings,
  updateNotificationSettings,
  listNotificationTypes,
  testNotification,
  previewNotification,
  listNotificationJobs,
  type NotificationSettings,
  type NotificationTypeMeta,
  type NotificationJob,
} from '@/lib/api';

const COMMON_TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Anchorage', 'Pacific/Honolulu', 'Europe/London', 'Europe/Berlin',
  'Asia/Tokyo', 'Australia/Sydney', 'UTC',
];

const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// ---------- cron <-> UI helpers ----------

type ParsedCron =
  | { kind: 'daily'; hour: number; minute: number }
  | { kind: 'weekly'; hour: number; minute: number; dow: number }
  | { kind: 'custom'; raw: string };

function parseCron(raw: string): ParsedCron {
  const parts = (raw || '').trim().split(/\s+/);
  if (parts.length !== 5) return { kind: 'custom', raw };
  const [m, h, dom, mon, dow] = parts;
  const minute = Number(m);
  const hour = Number(h);
  if (!Number.isInteger(minute) || !Number.isInteger(hour)) return { kind: 'custom', raw };
  if (minute < 0 || minute > 59 || hour < 0 || hour > 23) return { kind: 'custom', raw };
  if (dom !== '*' || mon !== '*') return { kind: 'custom', raw };
  if (dow === '*') return { kind: 'daily', hour, minute };
  const dowNum = Number(dow);
  if (Number.isInteger(dowNum) && dowNum >= 0 && dowNum <= 6) {
    return { kind: 'weekly', hour, minute, dow: dowNum };
  }
  return { kind: 'custom', raw };
}

function formatCron(p: ParsedCron): string {
  if (p.kind === 'daily') return `${p.minute} ${p.hour} * * *`;
  if (p.kind === 'weekly') return `${p.minute} ${p.hour} * * ${p.dow}`;
  return p.raw;
}

function hhmm(h: number, m: number): string {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function parseHHMM(value: string): { hour: number; minute: number } | null {
  const match = value.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

// ---------- page ----------

export default function NotificationsSettingsPage() {
  const [types, setTypes] = useState<NotificationTypeMeta[]>([]);
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [jobs, setJobs] = useState<NotificationJob[]>([]);
  const [schedulerRunning, setSchedulerRunning] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // detect the browser tz on first load so we can suggest it if the user
  // hasn't picked one yet (defaults to America/New_York server-side).
  const browserTz = useMemo(() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return null; }
  }, []);

  async function refreshJobs() {
    try {
      const r = await listNotificationJobs();
      setJobs(r.jobs);
      setSchedulerRunning(r.scheduler_running);
    } catch {
      // non-fatal; just leaves the jobs panel empty
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const [typesRes, settingsRes] = await Promise.all([
          listNotificationTypes(),
          getNotificationSettings(),
        ]);
        setTypes(typesRes.types);
        setSettings(settingsRes);
        await refreshJobs();
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function updateType(key: string, patch: Partial<{ enabled: boolean; cron: string }>) {
    setSettings(prev => prev && {
      ...prev,
      types: {
        ...prev.types,
        [key]: { ...prev.types[key], ...patch },
      },
    });
    setSuccess(null);
  }

  function updateTimezone(tz: string) {
    setSettings(prev => prev && { ...prev, timezone: tz });
    setSuccess(null);
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await updateNotificationSettings(settings);
      setSettings(res.settings);
      setSuccess(`Saved. Scheduler: +${res.scheduler.added ?? 0} / −${res.scheduler.removed ?? 0}.`);
      await refreshJobs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-slate-500">Loading…</div>;
  if (!settings) return <div className="text-rose-700">Failed to load settings: {error}</div>;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Notifications</h1>
          <p className="text-slate-600 mt-1">
            Schedule push notifications for study reminders, fresh papers, weekly recaps, and review nudges.
          </p>
        </div>
        <nav className="text-sm">
          <Link href="/settings/scope" className="text-sky-700 hover:underline">← Topic scope</Link>
        </nav>
      </header>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">{error}</div>}
      {success && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-2 text-sm">{success}</div>}

      {/* timezone */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Timezone</h2>
        <p className="text-xs text-slate-500">
          Every notification fires at the local time you pick, evaluated in this timezone.
          {browserTz && browserTz !== settings.timezone && (
            <> Your browser is in <code>{browserTz}</code> —{' '}
              <button
                type="button"
                onClick={() => updateTimezone(browserTz)}
                className="text-sky-700 hover:underline"
              >use that</button>.
            </>
          )}
        </p>
        <select
          value={settings.timezone}
          onChange={e => updateTimezone(e.target.value)}
          className="w-full max-w-sm px-3 py-2 border border-slate-300 rounded text-sm"
        >
          {COMMON_TIMEZONES.includes(settings.timezone) ? null : (
            <option value={settings.timezone}>{settings.timezone} (current)</option>
          )}
          {COMMON_TIMEZONES.map(tz => (
            <option key={tz} value={tz}>{tz}</option>
          ))}
        </select>
      </section>

      {/* one card per type */}
      <div className="space-y-4">
        {types.map(t => (
          <NotificationCard
            key={t.key}
            meta={t}
            entry={settings.types[t.key] ?? { enabled: false, cron: t.default_cron }}
            currentJob={jobs.find(j => j.type === t.key)}
            schedulerRunning={schedulerRunning}
            onChange={patch => updateType(t.key, patch)}
          />
        ))}
      </div>

      {/* footer: save */}
      <div className="bg-slate-100 border border-slate-200 rounded-lg p-4 flex items-center justify-between">
        <div className="text-sm text-slate-700">
          {Object.values(settings.types).filter(t => t.enabled).length} of {types.length} notification types enabled.
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="px-5 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save notifications'}
        </button>
      </div>

      {schedulerRunning === false && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg p-3 text-xs">
          The background scheduler isn't currently running on the server. Saved settings will be applied
          on the next restart. (Often this means the <code>SCHEDULER_DISABLED</code> env var is set —
          common in test / CI environments.)
        </div>
      )}
    </div>
  );
}

// ---------- card ----------

function NotificationCard({
  meta, entry, currentJob, schedulerRunning, onChange,
}: {
  meta: NotificationTypeMeta;
  entry: { enabled: boolean; cron: string };
  currentJob?: NotificationJob;
  schedulerRunning: boolean | null;
  onChange: (patch: Partial<{ enabled: boolean; cron: string }>) => void;
}) {
  const parsed = parseCron(entry.cron);
  const [busy, setBusy] = useState<null | 'preview' | 'test'>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [previewBody, setPreviewBody] = useState<string | null>(null);

  function setKind(kind: 'daily' | 'weekly') {
    if (parsed.kind === 'custom') return;          // never silently overwrite custom
    if (kind === 'daily') {
      onChange({ cron: formatCron({ kind: 'daily', hour: parsed.hour, minute: parsed.minute }) });
    } else {
      const dow = parsed.kind === 'weekly' ? parsed.dow : 0;
      onChange({ cron: formatCron({ kind: 'weekly', hour: parsed.hour, minute: parsed.minute, dow }) });
    }
  }

  function setTime(hhmmStr: string) {
    const t = parseHHMM(hhmmStr);
    if (!t || parsed.kind === 'custom') return;
    if (parsed.kind === 'daily') {
      onChange({ cron: formatCron({ kind: 'daily', hour: t.hour, minute: t.minute }) });
    } else if (parsed.kind === 'weekly') {
      onChange({ cron: formatCron({ kind: 'weekly', hour: t.hour, minute: t.minute, dow: parsed.dow }) });
    }
  }

  function setDow(dow: number) {
    if (parsed.kind !== 'weekly') return;
    onChange({ cron: formatCron({ kind: 'weekly', hour: parsed.hour, minute: parsed.minute, dow }) });
  }

  async function doPreview() {
    setBusy('preview');
    setFeedback(null);
    try {
      const res = await previewNotification(meta.key);
      if (!res.would_send) {
        setPreviewBody('(nothing to send right now — builder returned no payload)');
      } else {
        const payload = res.payload || {};
        const title = String(payload.title || '');
        const body = String(payload.body || '');
        setPreviewBody(`${title}\n${body}`);
      }
    } catch (e: any) {
      setFeedback(`Preview failed: ${e.message}`);
    } finally {
      setBusy(null);
    }
  }

  async function doTest() {
    setBusy('test');
    setFeedback(null);
    try {
      const res = await testNotification(meta.key);
      if (res.skipped) {
        setFeedback(`Skipped: ${res.skipped} (nothing to send right now)`);
      } else if (!res.ok) {
        setFeedback(`Failed: ${res.error || 'unknown error'}`);
      } else {
        const r = res.result || {};
        setFeedback(`Sent to ${r.sent ?? 0} device(s) · removed=${r.removed ?? 0} · failed=${r.failed ?? 0}`);
      }
    } catch (e: any) {
      setFeedback(`Test failed: ${e.message}`);
    } finally {
      setBusy(null);
    }
  }

  // time string in the input
  const timeValue = parsed.kind === 'custom' ? '' : hhmm(parsed.hour, parsed.minute);

  return (
    <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-grow">
          <h3 className="text-base font-semibold text-slate-900">{meta.label}</h3>
          <p className="text-sm text-slate-600">{meta.description}</p>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={entry.enabled}
            onChange={e => onChange({ enabled: e.target.checked })}
            className="w-4 h-4"
          />
          <span className="text-sm font-medium text-slate-700">
            {entry.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </label>
      </div>

      {/* schedule picker */}
      <div className={`grid gap-3 ${entry.enabled ? '' : 'opacity-50'}`}>
        {parsed.kind === 'custom' ? (
          <div className="space-y-1">
            <label className="text-xs text-slate-500">Custom cron (5 fields)</label>
            <input
              type="text"
              value={entry.cron}
              onChange={e => onChange({ cron: e.target.value })}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono"
              disabled={!entry.enabled}
            />
            <p className="text-xs text-slate-400">
              Cron doesn't match the simple daily/weekly pattern — editing as raw text. Format: <code>M H D Mo DOW</code>.
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label className="text-xs text-slate-500 block">Frequency</label>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setKind('daily')}
                  disabled={!entry.enabled}
                  className={`px-3 py-1.5 text-sm rounded border ${
                    parsed.kind === 'daily'
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-white border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  Daily
                </button>
                <button
                  type="button"
                  onClick={() => setKind('weekly')}
                  disabled={!entry.enabled}
                  className={`px-3 py-1.5 text-sm rounded border ${
                    parsed.kind === 'weekly'
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-white border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  Weekly
                </button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-500 block">Time</label>
              <input
                type="time"
                value={timeValue}
                onChange={e => setTime(e.target.value)}
                disabled={!entry.enabled}
                className="px-3 py-1.5 border border-slate-300 rounded text-sm"
              />
            </div>

            {parsed.kind === 'weekly' && (
              <div className="space-y-1">
                <label className="text-xs text-slate-500 block">Day</label>
                <div className="flex gap-1">
                  {DOW_LABELS.map((label, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setDow(idx)}
                      disabled={!entry.enabled}
                      className={`px-2 py-1 text-xs rounded border ${
                        parsed.dow === idx
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-white border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="text-xs text-slate-400 font-mono">
          cron: <span className="text-slate-600">{entry.cron}</span>
          {currentJob && (
            <span className="ml-3">
              · next: <span className="text-slate-600">{currentJob.next_run_time ?? '—'}</span>
            </span>
          )}
          {entry.enabled && !currentJob && schedulerRunning && (
            <span className="ml-3 text-amber-700">· not yet scheduled (save to register)</span>
          )}
        </div>
      </div>

      {/* preview + test */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
        <button
          type="button"
          onClick={doPreview}
          disabled={busy !== null}
          className="px-3 py-1.5 text-xs bg-white border border-slate-300 text-slate-700 rounded hover:bg-slate-50 disabled:opacity-50"
        >
          {busy === 'preview' ? 'Previewing…' : 'Preview content'}
        </button>
        <button
          type="button"
          onClick={doTest}
          disabled={busy !== null}
          className="px-3 py-1.5 text-xs bg-sky-100 text-sky-900 rounded hover:bg-sky-200 disabled:opacity-50"
        >
          {busy === 'test' ? 'Sending…' : 'Send test now'}
        </button>
        {feedback && (
          <span className="text-xs text-slate-600 ml-2">{feedback}</span>
        )}
      </div>

      {previewBody && (
        <pre className="text-xs bg-slate-50 border border-slate-200 rounded p-3 whitespace-pre-wrap font-sans">
          {previewBody}
        </pre>
      )}
    </section>
  );
}
