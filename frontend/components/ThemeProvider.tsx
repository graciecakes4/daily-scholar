'use client';

/**
 * ThemeProvider — applies the user's saved theme + font size (Phase 5 /
 * fd3) to <html> as `data-theme` / `data-font-size` attributes, which
 * globals.css keys its [data-theme="..."] variable blocks and
 * [data-font-size="..."] root font-size rules off of.
 *
 * Two-step application, same "no flash of wrong theme" trick as
 * next-themes: an inline blocking script in <head> (see layout.tsx)
 * synchronously applies whatever was cached in localStorage *before*
 * paint. This component then fetches the authoritative value from
 * GET /display/settings (works even logged-out — the backend resolves
 * to the '__local__' sentinel same as every other per-user setting) and
 * re-applies + re-caches in case the DB value differs from the cached
 * one (e.g. the user changed it on another device).
 *
 * Mounts once in the layout, alongside the other guard components.
 * Renders nothing — it's a side-effect-only component.
 */

import { useEffect } from 'react';
import { getDisplaySettings, type DisplaySettings } from '@/lib/api';

export const THEME_STORAGE_KEY = 'ds-display-settings';

// mirrors globals.css's --paper for each theme. The <meta name="theme-color">
// tag (mobile browser status bar / task-switcher card) is outside the CSS
// cascade entirely — Next's `viewport.themeColor` metadata export can only
// set a static value, so it has to be kept in sync here instead.
export const THEME_COLORS: Record<string, string> = {
  editorial: '#F2EBDD',
  dark: '#1C1812',
  observatory: '#0C0B09',
};

export function applyDisplaySettings(settings: DisplaySettings) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', settings.theme);
  document.documentElement.setAttribute('data-font-size', settings.font_size);
  const meta = document.querySelector('meta[name="theme-color"]');
  const color = THEME_COLORS[settings.theme] ?? THEME_COLORS.editorial;
  if (meta) meta.setAttribute('content', color);
}

function cacheDisplaySettings(settings: DisplaySettings) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // localStorage unavailable (private mode, etc.) — theme still applies
    // for this session, just doesn't survive a reload.
  }
}

export default function ThemeProvider() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const settings = await getDisplaySettings();
        if (cancelled) return;
        applyDisplaySettings(settings);
        cacheDisplaySettings(settings);
      } catch {
        // offline / logged-out-with-no-server / etc. — the inline script's
        // cached (or default) attributes already applied, so the app
        // still renders with a sensible theme; nothing further to do.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return null;
}
