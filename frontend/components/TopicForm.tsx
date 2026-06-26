'use client';

/**
 * Shared Topic editor used by both /topics/new (create) and
 * /topics/[id]/edit (update). Renders every Topic field as an editable
 * input or textarea (list fields take comma- or newline-separated input).
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  createTopic, updateTopic,
  type Topic, type TopicCreate,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

const DIFFICULTIES = ['easy', 'medium', 'hard'] as const;

export type TopicFormMode = 'create' | 'edit';

interface Props {
  mode: TopicFormMode;
  initial?: Topic;        // required when mode === 'edit'
}

interface FormState {
  id: string;
  name: string;
  stream: string;
  active: boolean;
  weight: string;
  keywords: string;
  arxiv_categories: string;
  recency_days: string;
  min_relevance: string;
  key_concepts: string;
  learning_objectives: string;
  resources: string;
  quiz_difficulty: string;
  prerequisites: string;
  visibility: 'private' | 'public';
}

function toLines(items: string[]): string {
  return (items || []).join('\n');
}

function fromLines(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map(s => s.trim())
    .filter(Boolean);
}

function initialFromTopic(topic?: Topic): FormState {
  return {
    id: topic?.id ?? '',
    name: topic?.name ?? '',
    stream: topic?.stream ?? '',
    active: topic?.active ?? true,
    weight: String(topic?.weight ?? 1.0),
    keywords: toLines(topic?.keywords ?? []),
    arxiv_categories: toLines(topic?.arxiv_categories ?? []),
    recency_days: String(topic?.recency_days ?? 30),
    min_relevance: String(topic?.min_relevance ?? 0.18),
    key_concepts: toLines(topic?.key_concepts ?? []),
    learning_objectives: toLines(topic?.learning_objectives ?? []),
    resources: toLines(topic?.resources ?? []),
    quiz_difficulty: topic?.quiz_difficulty ?? 'medium',
    prerequisites: toLines(topic?.prerequisites ?? []),
    visibility: topic?.visibility ?? 'private',
  };
}

export default function TopicForm({ mode, initial }: Props) {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [form, setForm] = useState<FormState>(initialFromTopic(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function patch<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  function buildPayload(): TopicCreate {
    return {
      // admins may supply an explicit slug; regular users let the server
      // auto-generate (server ignores client-supplied id for non-admins)
      id: isAdmin && form.id.trim() ? form.id.trim() : undefined,
      name: form.name.trim(),
      stream: form.stream.trim() || 'uncategorized',
      active: form.active,
      weight: parseFloat(form.weight) || 1.0,
      keywords: fromLines(form.keywords),
      arxiv_categories: fromLines(form.arxiv_categories),
      recency_days: parseInt(form.recency_days, 10) || 30,
      min_relevance: parseFloat(form.min_relevance) || 0.18,
      key_concepts: fromLines(form.key_concepts),
      learning_objectives: fromLines(form.learning_objectives),
      resources: fromLines(form.resources),
      quiz_difficulty: form.quiz_difficulty,
      prerequisites: fromLines(form.prerequisites),
      visibility: form.visibility,
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload();
      if (mode === 'create') {
        // only validate the slug format when an admin actually typed one;
        // regular users get a server-generated opaque id
        if (payload.id && !/^[a-z0-9][a-z0-9-]*$/.test(payload.id)) {
          throw new Error('id must be a lowercase slug (a-z, 0-9, -)');
        }
        await createTopic(payload);
        router.push('/topics');
      } else {
        // strip id from the payload for PUT
        const { id, ...update } = payload;
        await updateTopic(initial!.id, update);
        router.push('/topics');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-3xl">
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* identity */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Identity</h2>
        {/* slug field: only admins see it on create (regular users get a
            server-generated opaque id); shown read-only on edit so admins
            can see the slug, but it's immutable */}
        {(isAdmin || mode === 'edit') && (
          <Field
            label={mode === 'edit' ? 'ID (slug)' : 'ID (slug, admin override)'}
            hint={
              mode === 'edit'
                ? 'immutable after create'
                : 'optional — leave blank to auto-generate. lowercase, dashes only.'
            }
          >
            <input
              type="text"
              value={form.id}
              disabled={mode === 'edit'}
              onChange={e => patch('id', e.target.value)}
              placeholder={isAdmin ? 'leave blank to auto-generate' : 'my-new-topic'}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono disabled:bg-slate-100 disabled:text-slate-500"
            />
          </Field>
        )}
        <Field label="Name">
          <input
            type="text"
            value={form.name}
            onChange={e => patch('name', e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
            required
          />
        </Field>
        <Field
          label="Visibility"
          hint={
            form.visibility === 'private'
              ? 'only you can see this topic'
              : 'searchable + subscribable by other users'
          }
        >
          <select
            value={form.visibility}
            onChange={e => patch('visibility', e.target.value as 'private' | 'public')}
            className="w-full max-w-xs px-3 py-2 border border-slate-300 rounded text-sm"
          >
            <option value="private">Private</option>
            <option value="public">Public</option>
          </select>
        </Field>
        <Field label="Stream" hint="grouping label, e.g. 'foundations' or 'photometric_classification'">
          <input
            type="text"
            value={form.stream}
            onChange={e => patch('stream', e.target.value)}
            placeholder="uncategorized"
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
          />
        </Field>
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.active}
              onChange={e => patch('active', e.target.checked)}
            />
            Active
          </label>
          <Field label="Weight" hint="higher = bigger boost in relevance scoring" inline>
            <input
              type="number"
              step="0.1"
              value={form.weight}
              onChange={e => patch('weight', e.target.value)}
              className="w-20 px-2 py-1 border border-slate-300 rounded text-sm"
            />
          </Field>
        </div>
      </section>

      {/* paper discovery */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Paper Discovery</h2>
        <Field label="Keywords" hint="one per line, or comma-separated">
          <textarea
            value={form.keywords}
            onChange={e => patch('keywords', e.target.value)}
            rows={6}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono"
          />
        </Field>
        <Field label="arXiv categories" hint="e.g. astro-ph.IM, cs.LG">
          <textarea
            value={form.arxiv_categories}
            onChange={e => patch('arxiv_categories', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Recency days">
            <input
              type="number"
              value={form.recency_days}
              onChange={e => patch('recency_days', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
            />
          </Field>
          <Field label="Min relevance">
            <input
              type="number"
              step="0.01"
              value={form.min_relevance}
              onChange={e => patch('min_relevance', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
            />
          </Field>
        </div>
      </section>

      {/* learning content */}
      <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Learning Content</h2>
        <Field label="Key concepts" hint="one per line">
          <textarea
            value={form.key_concepts}
            onChange={e => patch('key_concepts', e.target.value)}
            rows={6}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
          />
        </Field>
        <Field label="Learning objectives" hint="one per line">
          <textarea
            value={form.learning_objectives}
            onChange={e => patch('learning_objectives', e.target.value)}
            rows={5}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
          />
        </Field>
        <Field label="Resources" hint="file paths relative to uploads/, or URLs">
          <textarea
            value={form.resources}
            onChange={e => patch('resources', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Quiz difficulty">
            <select
              value={form.quiz_difficulty}
              onChange={e => patch('quiz_difficulty', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm"
            >
              {DIFFICULTIES.map(d => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </Field>
          <Field label="Prerequisites (topic ids)" hint="one per line">
            <textarea
              value={form.prerequisites}
              onChange={e => patch('prerequisites', e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-slate-300 rounded text-sm font-mono"
            />
          </Field>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="px-5 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : mode === 'create' ? 'Create topic' : 'Save changes'}
        </button>
        <button
          type="button"
          onClick={() => router.push('/topics')}
          className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function Field({
  label, hint, children, inline,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  inline?: boolean;
}) {
  return (
    <label className={inline ? 'flex items-center gap-2' : 'block'}>
      <div className={inline ? 'text-sm font-medium text-slate-700' : 'flex items-baseline justify-between'}>
        <span className="text-sm font-medium text-slate-700">{label}</span>
        {hint && !inline && <span className="text-xs text-slate-400">{hint}</span>}
      </div>
      <div className={inline ? '' : 'mt-1'}>{children}</div>
    </label>
  );
}
