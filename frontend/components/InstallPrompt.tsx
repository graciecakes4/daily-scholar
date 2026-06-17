"use client";

/**
 * PWA install prompt.
 *
 * Two paths:
 *  - Chromium-family (Android Chrome, desktop Chrome/Edge, Brave, etc.) fires
 *    `beforeinstallprompt` — we capture and re-trigger it from a banner button.
 *  - iOS Safari never fires the event. We detect iOS + non-standalone-display
 *    and render a one-time instruction card explaining the Share → Add to Home
 *    Screen flow (the only way to install on iOS).
 *
 * Either banner can be dismissed; dismissals persist in localStorage for 14
 * days so we don't nag.
 */

import { useEffect, useState } from "react";

const DISMISS_KEY = "ds-install-dismissed-at";
const DISMISS_TTL_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

type DeferredEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function recentlyDismissed(): boolean {
  if (typeof window === "undefined") return true;
  const raw = window.localStorage.getItem(DISMISS_KEY);
  if (!raw) return false;
  const at = parseInt(raw, 10);
  if (Number.isNaN(at)) return false;
  return Date.now() - at < DISMISS_TTL_MS;
}

function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const iOS = /iPad|iPhone|iPod/.test(ua) && !(navigator as any).MSStream;
  const webkit = /WebKit/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
  return iOS && webkit;
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return true;
  // iOS-specific
  if ((navigator as any).standalone === true) return true;
  return window.matchMedia?.("(display-mode: standalone)").matches ?? false;
}

export default function InstallPrompt() {
  const [deferred, setDeferred] = useState<DeferredEvent | null>(null);
  const [showIos, setShowIos] = useState(false);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    if (recentlyDismissed() || isStandalone()) return;

    const onBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferred(e as DeferredEvent);
      setHidden(false);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);

    // iOS doesn't fire beforeinstallprompt — check for it after a delay
    const iosTimer = window.setTimeout(() => {
      if (isIosSafari() && !isStandalone()) {
        setShowIos(true);
        setHidden(false);
      }
    }, 4000);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.clearTimeout(iosTimer);
    };
  }, []);

  function dismiss() {
    setHidden(true);
    window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
  }

  async function install() {
    if (!deferred) return;
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted" || outcome === "dismissed") {
      setDeferred(null);
      setHidden(true);
      if (outcome === "dismissed") {
        window.localStorage.setItem(DISMISS_KEY, String(Date.now()));
      }
    }
  }

  if (hidden) return null;
  if (!deferred && !showIos) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:max-w-sm z-50">
      <div className="bg-slate-900 text-white rounded-2xl shadow-2xl border border-slate-800 p-4">
        <div className="flex items-start gap-3">
          <div className="text-3xl shrink-0">📚</div>
          <div className="flex-grow min-w-0">
            <div className="text-sm font-semibold">Install Daily Scholar</div>
            {showIos ? (
              <p className="text-xs text-slate-300 mt-1">
                Tap{" "}
                <span className="inline-block w-4 h-4 align-middle">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16" />
                  </svg>
                </span>{" "}
                in Safari's toolbar, then <strong>Add to Home Screen</strong>. (Required on iOS — push notifications need it.)
              </p>
            ) : (
              <p className="text-xs text-slate-300 mt-1">
                Get a one-tap shortcut on your home screen + offline access to your archive.
              </p>
            )}
            <div className="mt-3 flex items-center gap-2">
              {deferred && (
                <button
                  onClick={install}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-white text-slate-900 hover:bg-slate-100"
                >
                  Install
                </button>
              )}
              <button
                onClick={dismiss}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white"
              >
                Not now
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
