'use client';

/**
 * Display settings — theme + font size (Phase 5 / fd3, foundation slice).
 *
 * One card per registry entry (see backend/services/display.py), same
 * "fetch registry + current settings, edit locally, single Save" shape
 * as /settings/notifications. Applies the picked theme/font-size
 * immediately on click (via ThemeProvider's applyDisplaySettings) so the
 * picker doubles as a live preview — Save just persists it past reload.
 *
 * fd3 scoped a longer theme list than what shipped in the foundation
 * slice (pastel, muted, high-contrast, pride, colorful accents,
 * black-and-white, random) — soft_morning, noir, and brutalist landed
 * next as a registry addition in backend/services/display.py plus a
 * matching [data-theme="..."] block in globals.css. Adding more is the
 * same recipe; this page just needed the theme-card grid to wrap wider
 * (grid-cols-2/3) since it renders one card per registry entry.
 *
 * soft_morning also grew fd3's "colorful accents" picker (orange/rose/
 * sage/sky/lavender) — an extra section that only renders when the
 * selected theme's `accents` array (from GET /display/themes) is
 * non-empty. noir's set lands the same way, later.
 */

import { useEffect, useState } from 'react';
import {
  getDisplaySettings,
  updateDisplaySettings,
  listThemes,
  listFontSizes,
  type DisplaySettings,
  type ThemeMeta,
  type FontSizeMeta,
} from '@/lib/api';
import { applyDisplaySettings } from '@/components/ThemeProvider';

export default function DisplaySettingsPage() {
  const [themes, setThemes] = useState<ThemeMeta[]>([]);
  const [fontSizes, setFontSizes] = useState<FontSizeMeta[]>([]);
  const [settings, setSettings] = useState<DisplaySettings | null>(null);
  const [saved, setSaved] = useState<DisplaySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [themesRes, fontSizesRes, settingsRes] = await Promise.all([
          listThemes(),
          listFontSizes(),
          getDisplaySettings(),
        ]);
        setThemes(themesRes.themes);
        setFontSizes(fontSizesRes.font_sizes);
        setSettings(settingsRes);
        setSaved(settingsRes);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // live-preview: apply immediately on every pick, restore the saved
  // value on unmount so navigating away without saving doesn't leave a
  // stray preview theme applied.
  useEffect(() => {
    if (settings) applyDisplaySettings(settings);
    return () => {
      if (saved) applyDisplaySettings(saved);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  function pickTheme(theme: string) {
    setSettings(prev => {
      if (!prev) return prev;
      // carry the accent over if it's still valid for the newly-picked
      // theme (switching between two accent-capable themes someday);
      // otherwise fall back to that theme's first accent, or none at
      // all for themes with no accent picker.
      const accents = themes.find(t => t.key === theme)?.accents ?? [];
      const accent = accents.length === 0
        ? null
        : accents.some(a => a.key === prev.accent) ? prev.accent : accents[0].key;
      return { ...prev, theme, accent };
    });
    setSuccess(null);
  }

  function pickAccent(accent: string) {
    setSettings(prev => prev && { ...prev, accent });
    setSuccess(null);
  }

  function pickFontSize(font_size: string) {
    setSettings(prev => prev && { ...prev, font_size });
    setSuccess(null);
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await updateDisplaySettings(settings);
      setSettings(res);
      setSaved(res);
      applyDisplaySettings(res);
      setSuccess('Saved.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-muted">Loading…</div>;
  if (!settings) return <div className="text-rust">Failed to load settings: {error}</div>;

  const dirty = saved && (
    settings.theme !== saved.theme ||
    settings.font_size !== saved.font_size ||
    settings.accent !== saved.accent
  );
  const activeAccents = themes.find(t => t.key === settings.theme)?.accents ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-serif italic text-4xl font-semibold tracking-tight text-ink">Display</h1>
        <p className="text-muted mt-1.5 text-[15px] max-w-[52ch]">
          Pick a theme and text size. Changes preview immediately — nothing sticks until you save.
        </p>
      </header>

      {error && <div className="bg-rust/5 border border-rust/25 text-rust rounded-xl px-4 py-2.5 text-sm">{error}</div>}
      {success && <div className="bg-moss/5 border border-moss/25 text-moss rounded-xl px-4 py-2.5 text-sm">{success}</div>}

      {/* theme */}
      <section className="bg-paper-2 border border-rule rounded-2xl p-6 shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)] space-y-4">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-muted">Theme</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {themes.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => pickTheme(t.key)}
              className={`text-left rounded-2xl border p-4 transition-colors ${
                settings.theme === t.key
                  ? 'border-gold-dark bg-paper'
                  : 'border-rule bg-paper hover:border-gold'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="font-serif italic font-semibold text-lg text-ink">{t.label}</span>
                {settings.theme === t.key && (
                  <span className="text-[10px] font-mono uppercase tracking-wider text-gold-dark">Selected</span>
                )}
              </div>
              <p className="text-xs text-muted">{t.description}</p>
            </button>
          ))}
        </div>
      </section>

      {/* accent — only rendered for themes with a multi-hue picker
          (soft_morning today, noir later); the section disappears
          entirely for editorial/dark/observatory/brutalist. */}
      {activeAccents.length > 0 && (
        <section className="bg-paper-2 border border-rule rounded-2xl p-6 shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)] space-y-4">
          <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-muted">Accent</h2>
          <div className="flex flex-wrap gap-3">
            {activeAccents.map(a => (
              <button
                key={a.key}
                type="button"
                onClick={() => pickAccent(a.key)}
                title={a.label}
                aria-label={a.label}
                aria-pressed={settings.accent === a.key}
                className={`w-9 h-9 rounded-full border-2 transition-transform hover:scale-110 ${
                  settings.accent === a.key ? 'border-ink' : 'border-transparent'
                }`}
                style={{ backgroundColor: a.hex }}
              />
            ))}
          </div>
        </section>
      )}

      {/* font size */}
      <section className="bg-paper-2 border border-rule rounded-2xl p-6 shadow-[0_14px_34px_-18px_rgba(27,22,16,.18)] space-y-4">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-muted">Text size</h2>
        <div className="inline-flex flex-wrap bg-paper border border-rule rounded-full p-1 gap-1">
          {fontSizes.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => pickFontSize(f.key)}
              className={`px-4 py-2 text-[13px] font-semibold rounded-full transition-colors ${
                settings.font_size === f.key ? 'bg-ink text-paper-2' : 'text-muted hover:text-ink-2'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </section>

      {/* footer: save */}
      <div className="bg-paper-2 border border-rule rounded-2xl p-5 flex items-center justify-between flex-wrap gap-3">
        <div className="text-sm text-ink-2">
          {dirty ? 'Unsaved changes — previewing now.' : 'No unsaved changes.'}
        </div>
        <button
          onClick={save}
          disabled={saving || !dirty}
          className="px-6 py-2.5 bg-gold-dark text-white rounded-full text-sm font-semibold hover:brightness-90 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Save display settings'}
        </button>
      </div>
    </div>
  );
}
