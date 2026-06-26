'use client';

/**
 * Topic catalog — the unified Topic model browser.
 *
 * Lists every topic in the system, grouped by stream. Each row has quick
 * actions for soft-delete (toggle active), hard-delete, and edit. The
 * "import yaml" and "export yaml" controls are exposed here for the
 * YAML <-> DB round-trip path.
 *
 * Past topic reviews (the old /topics view) now live at /topics/archive.
 */

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  listTopics, listStreams, deleteTopic, updateTopic,
  importTopicsFromYaml, exportTopicsToYaml,
  unsubscribeTopic,
  type Topic,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

function streamDisplayName(stream: string): string {
  return stream
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

export default function TopicCatalogPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showOrphaned, setShowOrphaned] = useState(true);
  const [streamFilter, setStreamFilter] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // ownership check: caller can edit/delete iff admin or the row's owner.
  // `is_subscribed` from the API tells us when a non-system, non-our-own
  // topic is in our scope only because we subscribed to it — those we
  // can't edit (the owner can), but we CAN unsubscribe.
  function canEdit(t: Topic): boolean {
    if (isAdmin) return true;
    if (t.owner_user_id === null) return false;  // system → admin only
    if (t.is_subscribed) return false;           // subscribed-from-other → unsubscribe, don't edit
    return true;
  }

  async function handleUnsubscribe(topic: Topic) {
    setBusy(true);
    try {
      await unsubscribeTopic(topic.id);
      await fetchTopics();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void fetchTopics();
  }, [streamFilter, showOrphaned]);

  async function fetchTopics() {
    setLoading(true);
    setError(null);
    try {
      const data = await listTopics({
        stream: streamFilter || undefined,
        includeOrphaned: showOrphaned,
      });
      setTopics(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function toggleActive(topic: Topic) {
    setBusy(true);
    try {
      await updateTopic(topic.id, { active: !topic.active });
      await fetchTopics();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleHardDelete(topic: Topic) {
    if (!confirm(`Permanently delete topic "${topic.name}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await deleteTopic(topic.id, { hard: true });
      await fetchTopics();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport() {
    if (!confirm('Overwrite topics with the contents of config/topics/*.yaml? UI-only topics are untouched.')) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      const result = await importTopicsFromYaml();
      setStatusMsg(`Imported: ${result.inserted} new, ${result.updated} updated, ${result.marked_orphaned} marked orphaned.`);
      await fetchTopics();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleExport() {
    setBusy(true);
    setStatusMsg(null);
    try {
      const result = await exportTopicsToYaml();
      setStatusMsg(`Exported ${result.exported} topic(s) to ${result.directory}.`);
      await fetchTopics();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // group topics by stream for display
  const grouped: Record<string, Topic[]> = {};
  for (const t of topics) {
    if (!grouped[t.stream]) grouped[t.stream] = [];
    grouped[t.stream].push(t);
  }
  const orderedStreams = Object.keys(grouped).sort();

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Topics</h1>
          <p className="text-slate-600 mt-1">
            Each topic drives both paper discovery (keywords + arXiv categories) and review/quiz generation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            data-tour="topics-new"
            href="/topics/new"
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 transition-all"
          >
            + New topic
          </Link>
          <Link
            data-tour="topics-discover"
            href="/topics/discover"
            className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-all"
          >
            Discover
          </Link>
          <Link
            href="/topics/archive"
            className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-all"
          >
            Review history
          </Link>
        </div>
      </header>

      {/* controls */}
      <div data-tour="topics-filter" className="bg-white border border-slate-200 rounded-lg p-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-600">Stream:</label>
          <select
            value={streamFilter}
            onChange={e => setStreamFilter(e.target.value)}
            className="text-sm border border-slate-300 rounded px-2 py-1"
          >
            <option value="">All</option>
            {Object.keys(grouped).concat(streamFilter ? [streamFilter] : [])
              .filter((v, i, a) => a.indexOf(v) === i)
              .sort()
              .map(s => (
                <option key={s} value={s}>{streamDisplayName(s)}</option>
              ))}
          </select>
        </div>
        <label className="text-sm font-medium text-slate-600 flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showOrphaned}
            onChange={e => setShowOrphaned(e.target.checked)}
          />
          Include orphaned (YAML missing)
        </label>
        <div className="flex-grow" />
        <button
          onClick={handleImport}
          disabled={busy}
          className="px-3 py-1.5 text-sm bg-amber-100 text-amber-800 rounded hover:bg-amber-200 disabled:opacity-50"
          title="Re-sync topics table from config/topics/*.yaml"
        >
          Import YAML → DB
        </button>
        <button
          onClick={handleExport}
          disabled={busy}
          className="px-3 py-1.5 text-sm bg-sky-100 text-sky-800 rounded hover:bg-sky-200 disabled:opacity-50"
          title="Write current DB state out to config/topics/*.yaml"
        >
          Export DB → YAML
        </button>
      </div>

      {statusMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-2 text-sm">
          {statusMsg}
        </div>
      )}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-slate-500">Loading…</div>
      ) : topics.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-lg p-8 text-center text-slate-500">
          No topics yet. <Link href="/topics/new" className="text-slate-900 font-medium underline">Create one</Link>.
        </div>
      ) : (
        <div className="space-y-6">
          {orderedStreams.map(stream => (
            <section key={stream}>
              <h2 className="text-lg font-semibold text-slate-800 mb-2">
                {streamDisplayName(stream)}
                <span className="ml-2 text-sm font-normal text-slate-500">({grouped[stream].length})</span>
              </h2>
              <div className="bg-white border border-slate-200 rounded-lg divide-y divide-slate-100">
                {grouped[stream].map(topic => (
                  <TopicRow
                    key={topic.id}
                    topic={topic}
                    busy={busy}
                    canEdit={canEdit(topic)}
                    onToggleActive={() => toggleActive(topic)}
                    onHardDelete={() => handleHardDelete(topic)}
                    onUnsubscribe={() => handleUnsubscribe(topic)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function TopicRow({
  topic, busy, canEdit, onToggleActive, onHardDelete, onUnsubscribe,
}: {
  topic: Topic;
  busy: boolean;
  canEdit: boolean;
  onToggleActive: () => void;
  onHardDelete: () => void;
  onUnsubscribe: () => void;
}) {
  // Phase C/D ownership badge — system / your topic / subscribed
  const ownerBadge =
    topic.owner_user_id === null
      ? { label: 'System', cls: 'bg-slate-100 text-slate-700', title: 'Shared by the app' }
      : topic.is_subscribed
        ? { label: 'Subscribed', cls: 'bg-emerald-100 text-emerald-800', title: 'You subscribed to this topic via Discover' }
        : canEdit
          ? { label: 'Yours', cls: 'bg-sky-100 text-sky-800', title: 'You own this topic' }
          : { label: 'Shared', cls: 'bg-violet-100 text-violet-700', title: 'Public topic owned by another user' };

  return (
    <div className="p-4 flex items-start gap-4">
      <div className="flex-grow min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {canEdit ? (
            <Link
              href={`/topics/${encodeURIComponent(topic.id)}/edit`}
              className="font-semibold text-slate-900 hover:underline"
            >
              {topic.name}
            </Link>
          ) : (
            <span className="font-semibold text-slate-900">{topic.name}</span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded ${ownerBadge.cls}`} title={ownerBadge.title}>
            {ownerBadge.label}
          </span>
          {topic.visibility === 'private' && topic.owner_user_id !== null && (
            <span className="text-xs px-2 py-0.5 bg-slate-200 text-slate-700 rounded" title="Only you can see this topic">private</span>
          )}
          {!topic.active && (
            <span className="text-xs px-2 py-0.5 bg-slate-200 text-slate-600 rounded">inactive</span>
          )}
          {topic.created_via === 'ui' && (
            <span className="text-xs px-2 py-0.5 bg-violet-100 text-violet-700 rounded" title="Created via web UI">ui</span>
          )}
          {!topic.source_yaml_present && topic.created_via === 'yaml' && (
            <span className="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded" title="No matching YAML file on disk">orphaned</span>
          )}
          <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded">weight {topic.weight}</span>
          <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded">{topic.quiz_difficulty}</span>
        </div>
        <div className="mt-1 text-sm text-slate-500 truncate">
          {topic.id} · {topic.keywords.length} keywords · {topic.arxiv_categories.length} arXiv categories · {topic.key_concepts.length} concepts
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {topic.is_subscribed && (
          <button
            onClick={onUnsubscribe}
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded bg-white border border-slate-300 text-slate-700 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-700 disabled:opacity-50"
            title="Stop following this topic; the owner keeps it"
          >
            Unsubscribe
          </button>
        )}
        {canEdit && (
          <>
            <button
              onClick={onToggleActive}
              disabled={busy}
              className={`text-xs px-3 py-1.5 rounded border disabled:opacity-50 ${
                topic.active
                  ? 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
                  : 'bg-emerald-50 border-emerald-300 text-emerald-800 hover:bg-emerald-100'
              }`}
            >
              {topic.active ? 'Deactivate' : 'Activate'}
            </button>
            <Link
              href={`/topics/${encodeURIComponent(topic.id)}/edit`}
              className="text-xs px-3 py-1.5 rounded bg-white border border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              Edit
            </Link>
            <button
              onClick={onHardDelete}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded bg-white border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}
