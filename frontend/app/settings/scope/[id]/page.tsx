'use client';

/**
 * Single-scope editor.
 *
 * Owners get a full editing UI (name, description, mode, topic picker,
 * visibility toggle, delete, set-active). Non-owners (grantees and
 * users viewing a public scope) get a read-only view with a Fork button
 * so they can make their own editable copy.
 *
 * The mode-selector + topic picker section preserves the data-tour
 * attributes the ScopeTour points at — moved here from the old single-
 * scope page when the library page took over /settings/scope.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import {
  getScopeById,
  updateScopeById,
  setScopeVisibility,
  deleteScope,
  forkScope,
  createScope,
  setActiveScope,
  getActiveScope,
  listMyScopes,
  listTopics,
  type Scope,
  type ScopeMode,
  type ScopeVisibility,
  type Topic,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

function streamDisplayName(stream: string): string {
  return stream.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export default function ScopeEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  // "new" is a special route that means "draft a scope locally — only
  // POST to the server when the user hits Save". Navigating away without
  // saving leaves no row behind.
  const isDraft = params.id === 'new';
  const scopeId = isDraft ? null : Number(params.id);

  const [scope, setScope] = useState<Scope | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeScopeId, setActiveScopeId] = useState<number | null>(null);
  const [ownedIds, setOwnedIds] = useState<Set<number>>(new Set());
  const [name, setName] = useState(isDraft ? 'Untitled scope' : '');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<ScopeVisibility>('private');
  const [mode, setMode] = useState<ScopeMode>('all');
  const [selected, setSelected] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (isDraft) {
      // draft mode: no fetch for the scope itself. just load the topic
      // catalog so the picker can render. active-scope + library are
      // also cheap and useful (so we can show "is this active" badge
      // correctly once it's saved).
      (async () => {
        try {
          const [ts, act, lib] = await Promise.all([
            listTopics({ active: true }),
            getActiveScope(),
            listMyScopes(),
          ]);
          setTopics(ts);
          setActiveScopeId(act?.id ?? null);
          setOwnedIds(new Set(lib.filter(x => x.relation === 'owned').map(x => x.id)));
        } catch (e: any) {
          setError(e.message);
        } finally {
          setLoading(false);
        }
      })();
      return;
    }
    if (scopeId === null || !Number.isFinite(scopeId)) {
      setError('Invalid scope id.');
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [s, ts, act, lib] = await Promise.all([
          getScopeById(scopeId),
          listTopics({ active: true }),
          getActiveScope(),
          listMyScopes(),
        ]);
        setScope(s);
        setTopics(ts);
        setActiveScopeId(act?.id ?? null);
        setOwnedIds(new Set(lib.filter(x => x.relation === 'owned').map(x => x.id)));
        setName(s.name);
        setDescription(s.description ?? '');
        setVisibility(s.visibility);
        setMode(s.scope_mode);
        setSelected(s.scope_topic_ids);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [scopeId, isDraft]);

  // in draft mode the caller is always the owner-to-be of the new row, so
  // every input is editable and Save is enabled per the same rules as a
  // normal owned scope.
  const isOwner = isDraft || (scope ? ownedIds.has(scope.id) : false);
  const isAdmin = user?.role === 'admin';
  const canEdit = isOwner || isAdmin;
  const isActive = !isDraft && activeScopeId === scope?.id;

  const grouped = useMemo(() => {
    const out: Record<string, Topic[]> = {};
    for (const t of topics) {
      if (!out[t.stream]) out[t.stream] = [];
      out[t.stream].push(t);
    }
    return out;
  }, [topics]);

  function toggleSelected(id: string) {
    if (!canEdit) return;
    if (mode === 'silo') { setSelected([id]); return; }
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  function setRadioMode(next: ScopeMode) {
    if (!canEdit) return;
    setMode(next);
    setSuccess(null);
    if (next === 'all') setSelected([]);
    if (next === 'silo' && selected.length > 1) setSelected([selected[0]]);
  }

  async function save() {
    setSaving(true); setError(null); setSuccess(null);
    try {
      if (isDraft) {
        // first save of a draft: POST creates the row, then back to the
        // library — the new scope shows up there with the right owner badge.
        await createScope({
          name,
          description: description || null,
          visibility,
          scope_mode: mode,
          scope_topic_ids: mode === 'all' ? [] : selected,
        });
        router.push('/settings/scope/library');
        return;
      }
      await updateScopeById(scopeId!, {
        name,
        description: description || null,
        visibility,
        scope_mode: mode,
        scope_topic_ids: mode === 'all' ? [] : selected,
      });
      router.push('/settings/scope/library');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleVisibility() {
    const next: ScopeVisibility = visibility === 'public' ? 'private' : 'public';
    // in draft mode there's no row to PUT yet — just update the local
    // state so the visibility lands when the user hits Save.
    if (isDraft) {
      setVisibility(next);
      return;
    }
    if (!scope) return;
    try {
      const updated = await setScopeVisibility(scope.id, next);
      setScope(updated);
      setVisibility(updated.visibility);
      setSuccess(`Now ${updated.visibility}.`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete() {
    if (!scope) return;
    if (!confirm(`Delete "${scope.name}"? This cannot be undone.`)) return;
    try {
      await deleteScope(scope.id);
      router.push('/settings/scope/library');
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleFork() {
    if (!scope) return;
    try {
      const fk = await forkScope(scope.id);
      router.push(`/settings/scope/${fk.id}`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleSetActive() {
    if (!scope) return;
    try {
      await setActiveScope(scope.id);
      setActiveScopeId(scope.id);
      setSuccess('Set as active scope.');
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (loading) return <div className="text-slate-500">Loading…</div>;
  // draft mode renders the editor without a `scope` row; only the
  // existing-scope path needs the "not found" guard.
  if (!isDraft && !scope) {
    return (
      <div className="space-y-4">
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error ?? 'Scope not found.'}
        </div>
        <Link href="/settings/scope/library" className="text-sky-700 hover:underline text-sm">
          ← Back to library
        </Link>
      </div>
    );
  }

  const inScopeCount =
    mode === 'all' ? topics.length :
    mode === 'silo' ? Math.min(selected.length, 1) :
    selected.length;

  const saveDisabled =
    saving ||
    !canEdit ||
    !name.trim() ||
    (mode === 'silo' && selected.length !== 1) ||
    (mode === 'multi' && selected.length === 0);

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <Link href="/settings/scope/library" className="text-sky-700 hover:underline text-sm">
            ← Library
          </Link>
          <h1 className="text-3xl font-bold text-slate-900 mt-1 truncate">
            {isDraft ? 'New scope' : scope?.name}
          </h1>
          <p className="text-slate-600 mt-1 text-sm">
            {isDraft
              ? "Nothing is saved until you hit Save — navigate away to discard."
              : canEdit
                ? 'You own this scope.'
                : 'Read-only — fork to make your own copy.'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {!isDraft && !isActive && (
            <button
              type="button"
              onClick={handleSetActive}
              className="text-sm px-3 py-1.5 bg-slate-100 text-slate-700 rounded hover:bg-slate-200"
            >
              Set active
            </button>
          )}
          {!canEdit && (
            <button
              type="button"
              onClick={handleFork}
              className="text-sm px-3 py-1.5 bg-slate-900 text-white rounded hover:bg-slate-700"
            >
              Fork to my library
            </button>
          )}
          {canEdit && (
            <button
              type="button"
              onClick={toggleVisibility}
              className="text-sm px-3 py-1.5 bg-slate-100 text-slate-700 rounded hover:bg-slate-200"
              title={visibility === 'public' ? 'Make private' : 'Make public'}
            >
              {visibility === 'public' ? 'Make private' : 'Make public'}
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-2 text-sm">
          {success}
        </div>
      )}

      {/* name + description */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Details
        </h2>
        <label className="block">
          <span className="text-xs text-slate-600">Name</span>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            disabled={!canEdit}
            maxLength={200}
            className="mt-1 w-full px-3 py-2 border border-slate-300 rounded text-sm disabled:bg-slate-50 disabled:text-slate-500"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-600">Description (optional)</span>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            disabled={!canEdit}
            maxLength={2000}
            rows={3}
            className="mt-1 w-full px-3 py-2 border border-slate-300 rounded text-sm disabled:bg-slate-50 disabled:text-slate-500"
          />
        </label>
      </section>

      {/* mode selector */}
      <section data-tour="scope-mode" className="bg-white border border-slate-200 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Mode</h2>
        <ModeOption
          checked={mode === 'all'}
          onChange={() => setRadioMode('all')}
          label="All active topics"
          help="Every topic with active=true contributes to discovery and review."
          disabled={!canEdit}
        />
        <ModeOption
          checked={mode === 'multi'}
          onChange={() => setRadioMode('multi')}
          label="Multi-select"
          help="Pick a specific set of topics."
          disabled={!canEdit}
        />
        <ModeOption
          checked={mode === 'silo'}
          onChange={() => setRadioMode('silo')}
          label="Silo"
          help="Focus deeply on one topic."
          disabled={!canEdit}
        />
      </section>

      {/* topic picker */}
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
                      className={`flex items-center gap-3 px-3 py-2 rounded border ${
                        canEdit ? 'cursor-pointer' : 'cursor-default'
                      } ${
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
                        disabled={!canEdit}
                      />
                      <div className="flex-grow min-w-0">
                        <div className={`text-sm font-medium ${
                          selected.includes(t.id) ? 'text-white' : 'text-slate-900'
                        }`}>
                          {t.name}
                        </div>
                        <div className={`text-xs truncate ${
                          selected.includes(t.id) ? 'text-slate-300' : 'text-slate-500'
                        }`}>
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

      {/* footer */}
      <div className="bg-slate-100 border border-slate-200 rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="text-sm text-slate-700">
          {mode === 'all' && <span><strong>{topics.length}</strong> active topic(s) in scope.</span>}
          {mode === 'multi' && <span><strong>{inScopeCount}</strong> topic(s) selected.</span>}
          {mode === 'silo' && (
            selected.length === 1
              ? <span>Siloed on <strong>{topics.find(t => t.id === selected[0])?.name || selected[0]}</strong>.</span>
              : <span className="text-slate-500">Pick one topic to silo on.</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canEdit && !isDraft && (
            <button
              type="button"
              onClick={handleDelete}
              className="text-sm px-3 py-2 text-rose-600 hover:bg-rose-50 rounded"
            >
              Delete
            </button>
          )}
          <button
            data-tour="scope-save"
            onClick={save}
            disabled={saveDisabled}
            className="px-5 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
          >
            {saving ? 'Saving…' : isDraft ? 'Create' : 'Save'}
          </button>
        </div>
      </div>

      {scope && (
        <p className="text-xs text-slate-400">
          Last updated {new Date(scope.updated_at).toLocaleString()}.
          {scope.forked_from_scope_id && (
            <> Forked from scope #{scope.forked_from_scope_id}.</>
          )}
        </p>
      )}
    </div>
  );
}

function ModeOption({
  checked, onChange, label, help, disabled,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  help: string;
  disabled?: boolean;
}) {
  return (
    <label className={`flex items-start gap-3 ${disabled ? 'cursor-default opacity-70' : 'cursor-pointer'}`}>
      <input type="radio" checked={checked} onChange={onChange} disabled={disabled} className="mt-1" />
      <div>
        <div className="text-sm font-medium text-slate-900">{label}</div>
        <div className="text-xs text-slate-500">{help}</div>
      </div>
    </label>
  );
}
