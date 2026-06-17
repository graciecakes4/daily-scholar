/**
 * Offline shell page.
 *
 * Served by the service worker as the fallback for navigation requests when
 * (a) the network is unavailable AND (b) the requested page isn't in cache.
 * Pages the user has visited recently will still render from cache; this is
 * the "page you haven't seen before" fallback.
 */

import Link from "next/link";

export default function OfflinePage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="max-w-md text-center space-y-4">
        <div className="text-6xl">📡</div>
        <h1 className="text-2xl font-bold text-slate-900">You're offline</h1>
        <p className="text-slate-600">
          This page isn't cached yet. Try one of these — pages you've already
          visited still work without a connection.
        </p>
        <div className="flex flex-wrap justify-center gap-2 pt-2">
          <Link
            href="/"
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-700"
          >
            Dashboard
          </Link>
          <Link
            href="/papers"
            className="px-4 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-50"
          >
            Papers
          </Link>
          <Link
            href="/topics"
            className="px-4 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-50"
          >
            Topics
          </Link>
        </div>
        <p className="text-xs text-slate-400 pt-4">
          Actions you take while offline (saving a paper, marking a topic
          complete) are queued and replay automatically when you're back online.
        </p>
      </div>
    </div>
  );
}
