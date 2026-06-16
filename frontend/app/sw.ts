/**
 * Daily Scholar service worker.
 *
 * Built by @serwist/next from this source into public/sw.js at build time.
 * The defaultCache list from serwist covers the standard PWA app-shell + asset
 * caching; we extend it with custom runtime strategies for the FastAPI backend.
 *
 * Caching strategy summary:
 *   - App shell (HTML/CSS/JS/fonts/images): precache + stale-while-revalidate.
 *     Handled by serwist's defaultCache.
 *   - Backend GET endpoints (/topics, /papers/*, /archive/*, /stats, /user/*):
 *     NetworkFirst with 24h fallback so the UI stays responsive offline.
 *   - PDF blobs (backend /archive/papers/{id}/pdf): CacheFirst — papers are
 *     immutable once archived; cache hits are instant on revisit.
 *   - Mutating requests (POST/PUT/DELETE): pass-through with BackgroundSync
 *     queueing so offline taps replay when the network returns.
 *   - Navigation fallback: when no cache + no network, serve /offline.
 */

import { defaultCache } from "@serwist/next/worker";
import {
  type PrecacheEntry,
  type SerwistGlobalConfig,
  Serwist,
} from "serwist";
import {
  NetworkFirst,
  CacheFirst,
  ExpirationPlugin,
  BackgroundSyncPlugin,
} from "serwist";

// Type the SW global so TypeScript knows about __SW_MANIFEST.
declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}
declare const self: ServiceWorkerGlobalScope;

// Backend origin. In dev/local the frontend runs on :3000 and backend on :8000,
// so we match either by hostname. In production these are typically the same origin.
const BACKEND_HOSTS = new Set(["localhost", "127.0.0.1"]);
const BACKEND_PORT = "8000";

function isBackendGet(url: URL, request: Request): boolean {
  if (request.method !== "GET") return false;
  // same-origin? assume reverse-proxied behind one host
  if (url.origin === self.location.origin) {
    return (
      url.pathname.startsWith("/topics") ||
      url.pathname.startsWith("/papers") ||
      url.pathname.startsWith("/archive") ||
      url.pathname.startsWith("/stats") ||
      url.pathname.startsWith("/user/") ||
      url.pathname === "/daily" ||
      url.pathname === "/health"
    );
  }
  // dev: explicit backend port
  return BACKEND_HOSTS.has(url.hostname) && url.port === BACKEND_PORT;
}

function isPdfRequest(url: URL): boolean {
  return (
    url.pathname.endsWith(".pdf") ||
    /\/archive\/papers\/\d+\/pdf$/.test(url.pathname)
  );
}

function isMutatingBackendRequest(url: URL, request: Request): boolean {
  if (request.method === "GET" || request.method === "HEAD") return false;
  if (url.origin === self.location.origin) {
    return (
      url.pathname.startsWith("/topics") ||
      url.pathname.startsWith("/archive") ||
      url.pathname.startsWith("/papers") ||
      url.pathname.startsWith("/user/") ||
      url.pathname.startsWith("/push/") ||
      url.pathname.startsWith("/quiz/")
    );
  }
  return BACKEND_HOSTS.has(url.hostname) && url.port === BACKEND_PORT;
}

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  // serve /offline when a navigation request fails (offline + nothing cached)
  fallbacks: {
    entries: [
      {
        url: "/offline",
        matcher: ({ request }) => request.destination === "document",
      },
    ],
  },
  runtimeCaching: [
    // PDFs — cache-first, long TTL
    {
      matcher: ({ url, request }) =>
        request.method === "GET" && isPdfRequest(url),
      handler: new CacheFirst({
        cacheName: "ds-pdfs",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 50,
            maxAgeSeconds: 60 * 60 * 24 * 90, // 90 days
            purgeOnQuotaError: true,
          }),
        ],
      }),
    },
    // backend GET endpoints — network-first, 24h cache fallback
    {
      matcher: ({ url, request }) => isBackendGet(url, request),
      handler: new NetworkFirst({
        cacheName: "ds-api",
        networkTimeoutSeconds: 5,
        plugins: [
          new ExpirationPlugin({
            maxEntries: 100,
            maxAgeSeconds: 60 * 60 * 24, // 24h
          }),
        ],
      }),
    },
    // mutating backend requests — background sync queue when offline
    {
      matcher: ({ url, request }) => isMutatingBackendRequest(url, request),
      handler: async (params) => {
        // try the network first; if it fails the BG sync plugin captures and replays
        try {
          return await fetch(params.request.clone());
        } catch (e) {
          // background-sync replay handled by the plugin attached to a separate strategy
          throw e;
        }
      },
      method: "POST",
    },
    // fall back to serwist's default app-shell + asset caching
    ...defaultCache,
  ],
});

// Register a background-sync queue for failed mutations.
// Anything that fails the runtimeCaching handler above lands here for replay.
const bgSyncPlugin = new BackgroundSyncPlugin("ds-mutations", {
  maxRetentionTime: 24 * 60, // minutes — keep 24h of failed POSTs
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    isMutatingBackendRequest(url, event.request) &&
    !event.request.bodyUsed
  ) {
    event.respondWith(
      fetch(event.request.clone()).catch(async (err) => {
        await bgSyncPlugin.pushRequest({ request: event.request.clone() });
        // hint the caller that we queued the request
        return new Response(
          JSON.stringify({ queued: true, message: "Saved for replay when online" }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        );
      })
    );
  }
});

serwist.addEventListeners();
