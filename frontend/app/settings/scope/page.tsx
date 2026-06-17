'use client';

/**
 * Topic scope selector — silo / multi / all.
 *
 * The scope controls which topics drive paper discovery, topic review,
 * and quiz generation throughout the app. Persisted per-user on the
 * server (today, a single sentinel user).
 */

import { useEffect, useMemo, useState } from 'react';
import {
  getScope, updateScope, listTopics,
  type Scope, type ScopeMode, type Topic,
} from '@/lib/api';
import { useWebPush } from '@/hooks/useWebPush';

function streamDisplayName(stream: string): string {
  return stream.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export default function ScopeSettingsPage() {
  const [scope, setScope] = useState<Scope | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [mode, setMode] = useState<ScopeMode>('all');
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [scopeData, topicsData] = await Promise.all([
          getScope(),
          listTopics({ active: true }),
        ]);
        setScope(scopeData);
        setTopics(topicsData);
        setMode(scopeData.scope_mode);
        setSelected(scopeData.scope_topic_ids);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // group topics by stream for the picker
  const grouped = useMemo(() => {
    const out: Record<string, Topic[]> = {};
    for (const t of topics) {
      if (!out[t.stream]) out[t.stream] = [];
      out[t.stream].push(t);
    }
    return out;
  }, [topics]);

  function toggleSelected(id: string) {
    if (mode === 'silo') {
      setSelected([id]);
      return;
    }
    setSelected(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));
  }

  function setRadioMode(next: ScopeMode) {
    setMode(next);
    setSuccess(null);
    if (next === 'all') setSelected([]);
    if (next === 'silo' && selected.length > 1) setSelected([selected[0]]);
  }

  async function save() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = { scope_mode: mode, scope_topic_ids: mode === 'all' ? [] : selected };
      const updated = await updateScope(payload);
      setScope(updated);
      setSelected(updated.scope_topic_ids);
      setSuccess('Scope updated.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-slate-500">Loading…</div>;

  const inScopeCount =
    mode === 'all' ? topics.length :
    mode === 'silo' ? Math.min(selected.length, 1) :
    selected.length;

  const saveDisabled =
    saving ||
    (mode === 'silo' && selected.length !== 1) ||
    (mode === 'multi' && selected.length === 0);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">Topic scope</h1>
        <p className="text-slate-600 mt-1">
          Choose which topics drive paper discovery, reviews, and quiz generation.
        </p>
      </header>

      {error && <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">{error}</div>}
      {success && <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-2 text-sm">{success}</div>}

      {/* mode selector */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Mode</h2>
        <ModeOption
          checked={mode === 'all'}
          onChange={() => setRadioMode('all')}
          label="All active topics"
          help="Every topic with active=true contributes to discovery and review."
        />
        <ModeOption
          checked={mode === 'multi'}
          onChange={() => setRadioMode('multi')}
          label="Multi-select"
          help="Pick a specific set of topics."
        />
        <ModeOption
          checked={mode === 'silo'}
          onChange={() => setRadioMode('silo')}
          label="Silo"
          help="Focus deeply on one topic."
        />
      </section>

      {/* topic picker (hidden in 'all' mode) */}
      {mode !== 'all' && (
        <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
              {mode === 'silo' ? 'Select one topic' : 'Select topics'}
            </h2>
            <span className="text-xs text-slate-500">{selected.length} selected</span>
          </div>
          <div className="space-y-4">
            {Object.keys(grouped).sort().map(stream => (
              <div key={stream}>
                <h3 className="text-xs uppercase tracking-wide text-slate-400 mb-1">
                  {streamDisplayName(stream)}
                </h3>
                <div className="space-y-1">
                  {grouped[stream].map(t => (
                    <label
                      key={t.id}
                      className={`flex items-center gap-3 px-3 py-2 rounded cursor-pointer border ${
                        selected.includes(t.id)
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-white border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <input
                        type={mode === 'silo' ? 'radio' : 'checkbox'}
                        name="topic-pick"
                        checked={selected.includes(t.id)}
                        onChange={() => toggleSelected(t.id)}
                      />
                      <div className="flex-grow min-w-0">
                        <div className={`text-sm font-medium ${selected.includes(t.id) ? 'text-white' : 'text-slate-900'}`}>
                          {t.name}
                        </div>
                        <div className={`text-xs truncate ${selected.includes(t.id) ? 'text-slate-300' : 'text-slate-500'}`}>
                          {t.id}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* footer summary + save */}
      <div className="bg-slate-100 border border-slate-200 rounded-lg p-4 flex items-center justify-between">
        <div className="text-sm text-slate-700">
          {mode === 'all' && <span><strong>{topics.length}</strong> active topic(s) in scope.</span>}
          {mode === 'multi' && <span><strong>{inScopeCount}</strong> topic(s) selected.</span>}
          {mode === 'silo' && (
            selected.length === 1
              ? <span>Siloed on <strong>{topics.find(t => t.id === selected[0])?.name || selected[0]}</strong>.</span>
              : <span className="text-slate-500">Pick one topic to silo on.</span>
          )}
        </div>
        <button
          onClick={save}
          disabled={saveDisabled}
          className="px-5 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save scope'}
        </button>
      </div>

      {scope && (
        <p className="text-xs text-slate-400">
          Last updated {new Date(scope.updated_at).toLocaleString()} for <code>{scope.user_id}</code>.
        </p>
      )}

      <NotificationsSection />
    </div>
  );
}

function NotificationsSection() {
  const { supported, permission, subscribed, busy, error, subscribe, unsubscribe, sendTest } = useWebPush();

  // detect iOS Safari NOT yet running standalone — push only works on iOS after A2HS
  const iosNeedsInstall =
    typeof window !== 'undefined' &&
    /iPad|iPhone|iPod/.test(navigator.userAgent) &&
    !((navigator as any).standalone === true) &&
    !window.matchMedia?.('(display-mode: standalone)').matches;

  return (
    <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
      <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
        Notifications
      </h2>

      {!supported && (
        <p className="text-sm text-slate-600">
          Push notifications aren't supported in this browser. Try Chrome, Edge, Firefox, or Safari (16.4+).
        </p>
      )}

      {supported && iosNeedsInstall && !subscribed && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded p-3 text-sm">
          iOS requires installing the app to your home screen before push notifications can be enabled.
          Open in Safari → Share → <strong>Add to Home Screen</strong>, then come back here.
        </div>
      )}

      {supported && (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div className="text-sm font-medium text-slate-900">
                Daily-paper push notifications
              </div>
              <div className="text-xs text-slate-500">
                Status:{' '}
                <span className="font-mono">
                  permission={permission}, subscribed={String(subscribed)}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {!subscribed ? (
                <button
                  onClick={subscribe}
                  disabled={busy || permission === 'denied'}
                  className="px-4 py-2 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
                >
                  {busy ? 'Enabling…' : 'Enable notifications'}
                </button>
              ) : (
                <>
                  <button
                    onClick={sendTest}
                    disabled={busy}
                    className="px-3 py-1.5 bg-sky-100 text-sky-800 rounded text-sm hover:bg-sky-200 disabled:opacity-50"
                  >
                    Send test
                  </button>
                  <button
                    onClick={unsubscribe}
                    disabled={busy}
                    className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded text-sm hover:bg-slate-50 disabled:opacity-50"
                  >
                    Unsubscribe
                  </button>
                </>
              )}
            </div>
          </div>

          {permission === 'denied' && (
            <p className="text-xs text-rose-700">
              Notification permission was denied. Re-enable it in your browser's site settings, then refresh.
            </p>
          )}

          {error && (
            <p className="text-xs text-rose-700">{error}</p>
          )}
        </div>
      )}
    </section>
  );
}

function ModeOption({
  checked, onChange, label, help,
}: { checked: boolean; onChange: () => void; label: string; help: string }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input type="radio" checked={checked} onChange={onChange} className="mt-1" />
      <div>
        <div className="text-sm font-medium text-slate-900">{label}</div>
        <div className="text-xs text-slate-500">{help}</div>
      </div>
    </label>
  );
}
