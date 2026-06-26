'use client';

/**
 * /topics/discover — browse public topics from other users and subscribe.
 *
 * Subscriptions are live: when the owner edits the topic, the
 * subscriber's paper discovery / daily content picks up the changes
 * on the next query. Unsubscribe via the topic catalog (/topics).
 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { searchTopics, subscribeTopic, type Topic } from '@/lib/api';

export default function DiscoverPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Topic[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [subscribedIds, setSubscribedIds] = useState<Set<string>>(new Set());

  // debounce search so we don't fire on every keystroke
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await searchTopics(q);
        setResults(rows);
      } catch (e: any) {
        setError(e?.message || 'Search failed');
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  async function onSubscribe(topic: Topic) {
    setBusyId(topic.id);
    setError(null);
    try {
      await subscribeTopic(topic.id);
      setSubscribedIds(prev => new Set(prev).add(topic.id));
    } catch (e: any) {
      setError(e?.message || 'Subscribe failed');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Discover topics</h1>
          <p className="text-slate-600 mt-1">
            Find public topics shared by other Daily Scholar users.
            Subscribing adds them to your scope — when the owner updates
            the topic, your paper discovery follows along automatically.
          </p>
        </div>
        <nav className="text-sm">
          <Link href="/topics" className="text-sky-700 hover:underline">← My topics</Link>
        </nav>
      </header>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          autoFocus
          placeholder="Search by name…"
          className="w-full px-4 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:border-slate-900"
        />
        <p className="text-xs text-slate-500 mt-2">
          Currently matches topic names (case-insensitive). Keyword + concept search coming soon.
        </p>
      </div>

      {loading && <div className="text-slate-500">Searching…</div>}

      {results !== null && !loading && (
        results.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg p-8 text-center text-slate-500">
            No matching topics. They may not exist yet, be private, or already be in your scope.
          </div>
        ) : (
          <ul className="space-y-2">
            {results.map(topic => {
              const justSubscribed = subscribedIds.has(topic.id);
              return (
                <li key={topic.id} className="bg-white border border-slate-200 rounded-lg p-4 flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0 flex-grow">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-slate-900">{topic.name}</span>
                      <span className="text-xs px-2 py-0.5 bg-violet-100 text-violet-700 rounded">Shared</span>
                      <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded">weight {topic.weight}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {topic.keywords.length} keywords · {topic.arxiv_categories.length} arXiv categories · {topic.key_concepts.length} concepts · {topic.stream}
                    </div>
                    {topic.keywords.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {topic.keywords.slice(0, 8).map(kw => (
                          <span key={kw} className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded">
                            {kw}
                          </span>
                        ))}
                        {topic.keywords.length > 8 && (
                          <span className="text-xs text-slate-400">+{topic.keywords.length - 8} more</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0">
                    {justSubscribed ? (
                      <span className="text-xs px-3 py-1.5 bg-emerald-100 text-emerald-800 rounded font-medium">
                        ✓ Subscribed
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSubscribe(topic)}
                        disabled={busyId !== null}
                        className="px-3 py-1.5 bg-slate-900 text-white rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
                      >
                        {busyId === topic.id ? 'Subscribing…' : 'Subscribe'}
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )
      )}

      {results === null && !loading && (
        <div className="text-sm text-slate-500 italic">
          Start typing to search.
        </div>
      )}
    </div>
  );
}
