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
  NetworkFirst,
  CacheFirst,
  ExpirationPlugin,
} from "serwist";
import { Queue } from "@serwist/background-sync";

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
    // fall back to serwist's default app-shell + asset caching
    ...defaultCache,
  ],
});

// Background-sync queue for failed mutations. Anything we push here is
// retried automatically by the browser when the network comes back, up to
// maxRetentionTime minutes later.
const mutationQueue = new Queue("ds-mutations", {
  maxRetentionTime: 24 * 60, // 24h
});

// Custom fetch listener for mutating backend requests: try network first,
// queue for replay on failure. Lives outside serwist.runtimeCaching because
// that subsystem is GET-focused.
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method === "GET" || req.method === "HEAD") return;
  const url = new URL(req.url);
  if (!isMutatingBackendRequest(url, req)) return;

  event.respondWith(
    (async () => {
      try {
        return await fetch(req.clone());
      } catch {
        await mutationQueue.pushRequest({ request: req.clone() });
        return new Response(
          JSON.stringify({ queued: true, message: "Saved for replay when online" }),
          { status: 202, headers: { "Content-Type": "application/json" } }
        );
      }
    })()
  );
});

serwist.addEventListeners();
