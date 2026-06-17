"use client";

/**
 * Web Push subscription management.
 *
 * Surfaces the four operations a UI needs:
 *   - permission state (default | granted | denied)
 *   - whether this device is currently subscribed
 *   - subscribe() / unsubscribe()
 *   - sendTest() to fire a sanity-check push
 *
 * The actual VAPID public key is fetched from the backend lazily on subscribe
 * so we don't bake it into the client bundle.
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Permission = "default" | "granted" | "denied" | "unsupported";

function detectPlatform(): string {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent;
  if (/iPad|iPhone|iPod/.test(ua)) return "ios";
  if (/Mac OS X/.test(ua)) return "macos";
  if (/Android/.test(ua)) return "android";
  return "desktop";
}

/** urlsafe-base64 (VAPID format) → Uint8Array, which is what PushManager.subscribe wants. */
function urlBase64ToUint8Array(b64: string): Uint8Array {
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function fetchVapidPublicKey(): Promise<string> {
  const res = await fetch(`${API_BASE}/push/vapid-public-key`);
  if (!res.ok) throw new Error(`VAPID key fetch failed: ${res.status}`);
  const data = await res.json();
  return data.public_key as string;
}

export function useWebPush() {
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState<Permission>("default");
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // initial detection — run once on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const ok =
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window;
    setSupported(ok);
    if (!ok) {
      setPermission("unsupported");
      return;
    }
    setPermission(Notification.permission as Permission);

    // check whether this device already has an active subscription
    (async () => {
      try {
        const reg = await navigator.serviceWorker.ready;
        const existing = await reg.pushManager.getSubscription();
        setSubscribed(!!existing);
      } catch (e: any) {
        // not fatal — SW may not be registered yet (dev mode)
      }
    })();
  }, []);

  const subscribe = useCallback(async () => {
    if (!supported) return;
    setBusy(true);
    setError(null);
    try {
      // request permission first — required gesture context
      const perm = await Notification.requestPermission();
      setPermission(perm as Permission);
      if (perm !== "granted") {
        throw new Error("Notification permission denied.");
      }

      const reg = await navigator.serviceWorker.ready;
      const publicKey = await fetchVapidPublicKey();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        // BufferSource cast: TS strict mode is fussy about Uint8Array<ArrayBufferLike>
        // vs Uint8Array<ArrayBuffer>; both are valid at runtime
        applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
      });

      const json = sub.toJSON();
      const res = await fetch(`${API_BASE}/push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: json.endpoint,
          keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
          platform: detectPlatform(),
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `subscribe failed: ${res.status}`);
      }
      setSubscribed(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [supported]);

  const unsubscribe = useCallback(async () => {
    if (!supported) return;
    setBusy(true);
    setError(null);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await fetch(`${API_BASE}/push/unsubscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      setSubscribed(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [supported]);

  const sendTest = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/push/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Daily Scholar test",
          body: "If you see this, push notifications are wired up.",
          url: "/",
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `test push failed: ${res.status}`);
      }
      const result = await res.json();
      if (result.sent === 0) {
        throw new Error("No active subscriptions for this user — subscribe first.");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  return { supported, permission, subscribed, busy, error, subscribe, unsubscribe, sendTest };
}
