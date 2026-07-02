'use client';

/**
 * Notifications settings — one card per notification type from the
 * server-side registry. Each card leads with a plain-English schedule
 * sentence ("Every day at 9:00 AM") built from the underlying cron
 * expression; the raw cron is tucked behind a small "i" info affordance
 * for devs/power users rather than shown as the primary UI. A Preview
 * button renders the payload without sending, and a Test button fires
 * through the real push pipeline.
 *
 * The cron expression is still the source of truth on disk — the UI
 * helpers below parse/format the subset of cron we actually expose
 * ("M H * * *" for daily, "M H * * DOW" for weekly). If a power user
 * has hand-edited the JSON to something exotic, the friendly picker
 * hides itself and we fall back to a raw, editable cron field so we
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

const DOW_SHORT = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const DOW_FULL = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

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

/** 24h hour -> { hour12, ap } for the friendly stepper. */
function to12h(hour: number): { hour12: number; ap: 'AM' | 'PM' } {
  const ap: 'AM' | 'PM' = hour >= 12 ? 'PM' : 'AM';
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  return { hour12, ap };
}

function to24h(hour12: number, ap: 'AM' | 'PM'): number {
  const h = hour12 % 12;
  return ap === 'PM' ? h + 12 : h;
}

function fmt12(hour: number, minute: number): string {
  const { hour12, ap } = to12h(hour);
  return `${hour12}:${String(minute).padStart(2, '0')} ${ap}`;
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

  if (loading) return <div className="text-muted">Loading…</div>;
  if (!settings) return <div className="text-rust">Failed to load settings: {error}</div>;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-serif italic text-4xl font-semibold tracking-tight text-ink">Notifications</h1>
          <p className="text-muted mt-1.5 text-[15px] max-w-[52ch]">
            Schedule push notifications for study reminders, fresh papers, weekly recaps, and review nudges — set in plain English.
          </p>
        </div>
        <nav className="text-sm">
          <Link href="/settings/scope" className="text-gold-dark hover:underline">← Topic scope</Link>
        </nav>
      </header>

      {error && <div className="bg-rust/5 border border-rust/25 text-rust rounded-xl px-4 py-2.5 text-sm">{error}</div>}
      {success && <div className="bg-moss/5 border border-moss/25 text-moss rounded-xl px-4 py-2.5 text-sm">{success}</div>}

      {/* timezone */}
      <section className="bg-paper-2 border border-rule rounded-2xl p-6 shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)] space-y-3">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-muted">Timezone</h2>
        <p className="text-xs text-muted">
          Every notification fires at the local time you pick, evaluated in this timezone.
          {browserTz && browserTz !== settings.timezone && (
            <> Your browser is in <code className="font-mono">{browserTz}</code> —{' '}
              <button
                type="button"
                onClick={() => updateTimezone(browserTz)}
                className="text-gold-dark hover:underline"
              >use that</button>.
            </>
          )}
        </p>
        <select
          value={settings.timezone}
          onChange={e => updateTimezone(e.target.value)}
          className="w-full max-w-sm px-3.5 py-2.5 border border-rule rounded-xl bg-paper text-sm text-ink"
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
      <div className="space-y-5">
        {types.map(t => (
          <NotificationCard
            key={t.key}
            meta={t}
            entry={settings.types[t.key] ?? { enabled: false, cron: t.default_cron }}
            currentJob={jobs.find(j => j.type === t.key)}
            schedulerRunning={schedulerRunning}
            timezone={settings.timezone}
            onChange={patch => updateType(t.key, patch)}
          />
        ))}
      </div>

      {/* footer: save */}
      <div className="bg-paper-2 border border-rule rounded-2xl p-5 flex items-center justify-between flex-wrap gap-3">
        <div className="text-sm text-ink-2">
          {Object.values(settings.types).filter(t => t.enabled).length} of {types.length} notification types enabled.
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="px-6 py-2.5 bg-gold-dark text-white rounded-full text-sm font-semibold hover:bg-[#734f14] disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Save notifications'}
        </button>
      </div>

      {schedulerRunning === false && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-xl p-3.5 text-xs">
          The background scheduler isn't currently running on the server. Saved settings will be applied
          on the next restart. (Often this means the <code className="font-mono">SCHEDULER_DISABLED</code> env var is set —
          common in test / CI environments.)
        </div>
      )}
    </div>
  );
}

// ---------- card ----------

function NotificationCard({
  meta, entry, currentJob, schedulerRunning, timezone, onChange,
}: {
  meta: NotificationTypeMeta;
  entry: { enabled: boolean; cron: string };
  currentJob?: NotificationJob;
  schedulerRunning: boolean | null;
  timezone: string;
  onChange: (patch: Partial<{ enabled: boolean; cron: string }>) => void;
}) {
  const parsed = parseCron(entry.cron);
  const [busy, setBusy] = useState<null | 'preview' | 'test'>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [previewBody, setPreviewBody] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);

  function setKind(kind: 'daily' | 'weekly') {
    if (parsed.kind === 'custom') return;          // never silently overwrite custom
    if (kind === 'daily') {
      onChange({ cron: formatCron({ kind: 'daily', hour: parsed.hour, minute: parsed.minute }) });
    } else {
      const dow = parsed.kind === 'weekly' ? parsed.dow : 0;
      onChange({ cron: formatCron({ kind: 'weekly', hour: parsed.hour, minute: parsed.minute, dow }) });
    }
  }

  function setDow(dow: number) {
    if (parsed.kind !== 'weekly') return;
    onChange({ cron: formatCron({ kind: 'weekly', hour: parsed.hour, minute: parsed.minute, dow }) });
  }

  function stepHour(delta: number) {
    if (parsed.kind === 'custom') return;
    const { hour12, ap } = to12h(parsed.hour);
    let next12 = hour12 + delta;
    if (next12 > 12) next12 = 1;
    if (next12 < 1) next12 = 12;
    const hour = to24h(next12, ap);
    applyTime(hour, parsed.minute);
  }

  function stepMinute(delta: number) {
    if (parsed.kind === 'custom') return;
    let minute = parsed.minute + delta * 5;
    if (minute >= 60) minute = 0;
    if (minute < 0) minute = 55;
    applyTime(parsed.hour, minute);
  }

  function setAmPm(ap: 'AM' | 'PM') {
    if (parsed.kind === 'custom') return;
    const { hour12 } = to12h(parsed.hour);
    applyTime(to24h(hour12, ap), parsed.minute);
  }

  function applyTime(hour: number, minute: number) {
    if (parsed.kind === 'daily') {
      onChange({ cron: formatCron({ kind: 'daily', hour, minute }) });
    } else if (parsed.kind === 'weekly') {
      onChange({ cron: formatCron({ kind: 'weekly', hour, minute, dow: parsed.dow }) });
    }
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
      if (res.skipped || res.result?.skipped) {
        setFeedback(`Skipped: ${res.skipped ?? res.result?.skipped} (nothing to send right now)`);
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

  const ap = parsed.kind !== 'custom' ? to12h(parsed.hour).ap : 'AM';
  const hour12 = parsed.kind !== 'custom' ? to12h(parsed.hour).hour12 : 12;
  const minute = parsed.kind !== 'custom' ? parsed.minute : 0;

  const headline = parsed.kind === 'daily'
    ? <>Every day at <b className="font-semibold text-gold-dark not-italic">{fmt12(parsed.hour, parsed.minute)}</b></>
    : parsed.kind === 'weekly'
      ? <>Every {DOW_FULL[parsed.dow]} at <b className="font-semibold text-gold-dark not-italic">{fmt12(parsed.hour, parsed.minute)}</b></>
      : null;

  const scheduleNote = currentJob
    ? `next: ${currentJob.next_run_time ?? '—'}`
    : entry.enabled && schedulerRunning
      ? 'not yet scheduled (save to register)'
      : null;

  return (
    <section
      className="bg-paper-2 border border-rule rounded-[22px] p-7 shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)] space-y-1"
      style={{ opacity: entry.enabled ? 1 : 0.6 }}
    >
      <div className="flex items-start justify-between gap-4 flex-wrap mb-1.5">
        <div>
          <h3 className="font-serif italic font-semibold text-2xl text-ink">{meta.label}</h3>
          <p className="text-[13.5px] text-muted mt-0.5">{meta.description}</p>
        </div>
        <label className="relative flex-shrink-0 cursor-pointer">
          <input
            type="checkbox"
            checked={entry.enabled}
            onChange={e => onChange({ enabled: e.target.checked })}
            className="peer sr-only"
          />
          <span className="block w-[46px] h-[26px] rounded-full bg-rule peer-checked:bg-gold-dark transition-colors relative after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:w-5 after:h-5 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:after:translate-x-5" />
        </label>
      </div>

      {parsed.kind === 'custom' ? (
        <div className="space-y-1.5 py-3">
          <label className="text-xs text-muted">Custom cron (5 fields) — doesn't match the simple daily/weekly pattern, editing as raw text.</label>
          <input
            type="text"
            value={entry.cron}
            onChange={e => onChange({ cron: e.target.value })}
            className="w-full px-3.5 py-2.5 border border-rule rounded-xl text-sm font-mono bg-paper text-ink"
            disabled={!entry.enabled}
          />
          <p className="text-xs text-muted">Format: <code className="font-mono">M H D Mo DOW</code>.</p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-5 relative">
            <p className="font-serif italic text-[23px] text-ink m-0">{headline}</p>
            <button
              type="button"
              onClick={() => setInfoOpen(o => !o)}
              className="relative flex-shrink-0 w-[18px] h-[18px] rounded-full border border-muted text-muted text-[11px] font-semibold flex items-center justify-center hover:border-ink hover:text-ink transition-colors"
              aria-label="Show cron expression"
            >
              i
              {infoOpen && (
                <span className="absolute top-6 left-0 bg-ink text-paper-2 font-mono text-[11px] px-3 py-2 rounded-lg whitespace-nowrap z-10 shadow-lg text-left">
                  <span className="block font-sans text-[9px] uppercase tracking-wider text-[#C9BBA6] mb-0.5">for developers</span>
                  {entry.cron}
                </span>
              )}
            </button>
          </div>

          {scheduleNote && (
            <p className={`text-xs -mt-3 mb-4 ${currentJob ? 'text-muted' : 'text-gold-dark'}`}>{scheduleNote}</p>
          )}

          <div className="bg-paper border border-rule rounded-2xl p-5 mb-5 space-y-4">
            <div className="inline-flex bg-paper-2 border border-rule rounded-full p-1">
              <button
                type="button"
                onClick={() => setKind('daily')}
                disabled={!entry.enabled}
                className={`px-4 py-2 text-[13px] font-semibold rounded-full transition-colors ${
                  parsed.kind === 'daily' ? 'bg-ink text-paper-2' : 'text-muted hover:text-ink-2'
                }`}
              >
                Every day
              </button>
              <button
                type="button"
                onClick={() => setKind('weekly')}
                disabled={!entry.enabled}
                className={`px-4 py-2 text-[13px] font-semibold rounded-full transition-colors ${
                  parsed.kind === 'weekly' ? 'bg-ink text-paper-2' : 'text-muted hover:text-ink-2'
                }`}
              >
                Every week
              </button>
            </div>

            {parsed.kind === 'weekly' && (
              <div className="flex gap-2">
                {DOW_SHORT.map((label, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setDow(idx)}
                    disabled={!entry.enabled}
                    className={`w-9 h-9 rounded-full border font-mono text-xs font-semibold transition-all ${
                      parsed.dow === idx
                        ? 'bg-ink border-ink text-paper-2 scale-[1.06]'
                        : 'bg-paper-2 border-rule text-muted hover:border-gold'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3.5">
              <div className="flex flex-col items-center gap-0.5">
                <button type="button" disabled={!entry.enabled} onClick={() => stepHour(1)} className="w-8 h-5 bg-paper-2 border border-rule text-gold-dark rounded-md text-[11px] leading-none">▲</button>
                <div className="font-serif font-semibold text-[32px] text-ink w-[54px] text-center leading-tight">{hour12}</div>
                <button type="button" disabled={!entry.enabled} onClick={() => stepHour(-1)} className="w-8 h-5 bg-paper-2 border border-rule text-gold-dark rounded-md text-[11px] leading-none">▼</button>
              </div>
              <div className="font-serif text-[32px] text-muted mt-1.5">:</div>
              <div className="flex flex-col items-center gap-0.5">
                <button type="button" disabled={!entry.enabled} onClick={() => stepMinute(1)} className="w-8 h-5 bg-paper-2 border border-rule text-gold-dark rounded-md text-[11px] leading-none">▲</button>
                <div className="font-serif font-semibold text-[32px] text-ink w-[54px] text-center leading-tight">{String(minute).padStart(2, '0')}</div>
                <button type="button" disabled={!entry.enabled} onClick={() => stepMinute(-1)} className="w-8 h-5 bg-paper-2 border border-rule text-gold-dark rounded-md text-[11px] leading-none">▼</button>
              </div>
              <div className="flex flex-col gap-1 ml-1">
                {(['AM', 'PM'] as const).map(v => (
                  <button
                    key={v}
                    type="button"
                    disabled={!entry.enabled}
                    onClick={() => setAmPm(v)}
                    className={`px-3 py-1.5 text-[10.5px] font-semibold rounded-lg border transition-colors ${
                      ap === v ? 'bg-gold-dark border-gold-dark text-white' : 'bg-paper-2 border-rule text-muted'
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* preview + test */}
      <div className="flex items-center gap-2.5 pt-1 flex-wrap">
        <button
          type="button"
          onClick={doPreview}
          disabled={busy !== null}
          className="px-4 py-2 text-xs font-semibold bg-paper-2 border border-rule text-ink-2 rounded-full hover:border-gold disabled:opacity-50 transition-colors"
        >
          {busy === 'preview' ? 'Previewing…' : 'Preview content'}
        </button>
        <button
          type="button"
          onClick={doTest}
          disabled={busy !== null}
          className="px-4 py-2 text-xs font-semibold bg-gold-dark text-white rounded-full hover:bg-[#734f14] disabled:opacity-50 transition-colors"
        >
          {busy === 'test' ? 'Sending…' : 'Send test now'}
        </button>
        {feedback && (
          <span className="text-xs text-muted ml-1">{feedback}</span>
        )}
      </div>

      {previewBody && (
        <pre className="text-xs bg-paper border border-rule rounded-xl p-4 whitespace-pre-wrap font-sans text-ink-2 mt-2">
          {previewBody}
        </pre>
      )}
    </section>
  );
}
