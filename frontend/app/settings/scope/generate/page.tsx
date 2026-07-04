'use client';

/**
 * /settings/scope/generate — AI-assisted scope creation.
 *
 * Previously the only "type a description, get keywords/arXiv categories
 * generated for you" flow was the first-run onboarding wizard
 * (POST /onboarding/generate-topic → POST /onboarding/complete), which
 * only ever ran once per account. That generation endpoint isn't actually
 * onboarding-gated server-side — it just checks for a real signed-up user
 * — so this page reuses it directly via the existing generateTopicDraft()
 * client, available any time from Settings > Scope.
 *
 * Flow: title + description in → generateTopicDraft() drafts keywords /
 * arXiv categories / key concepts → the user reviews and edits the draft
 * as chips (nothing is saved yet) → approving creates a new Topic, then
 * wraps it in a new single-topic ("silo") Scope. The new scope lands in
 * the library but does NOT become active — the user switches to it
 * manually when ready, same as forking or picking a starter scope.
 *
 * Keywords / categories / key concepts are edited as chips rather than a
 * free-text box: click a chip to select it, then Edit or Delete; a
 * separate "+ Add" chip reveals a text input with autocomplete
 * suggestions — recommendations only ever show up in the add flow, not
 * while editing an existing chip. Suggestions are drawn from the user's
 * visible topic catalog (real keywords/concepts already in use), plus a
 * static arXiv taxonomy list for the categories field specifically.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import {
  generateTopicDraft,
  createTopic,
  createScope,
  listTopics,
  type ScopeVisibility,
} from '@/lib/api';
import { ARXIV_CATEGORIES } from '@/lib/arxivCategories';
import ChipListEditor from '@/components/ChipListEditor';

const MIN_DESCRIPTION_CHARS = 10;

// case-insensitive dedupe that keeps the first-seen casing
function dedupe(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

type Stage = 'input' | 'review';

export default function GenerateScopePage() {
  const router = useRouter();

  const [stage, setStage] = useState<Stage>('input');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<ScopeVisibility>('private');

  const [keywords, setKeywords] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [concepts, setConcepts] = useState<string[]>([]);

  // suggestion pools for the "+ Add" autocomplete, built from every topic
  // the user can currently see — real keywords/concepts already in use,
  // rather than anything fabricated
  const [catalogKeywords, setCatalogKeywords] = useState<string[]>([]);
  const [catalogConcepts, setCatalogConcepts] = useState<string[]>([]);
  const [catalogCategories, setCatalogCategories] = useState<string[]>([]);

  const [generating, setGenerating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTopics()
      .then(topics => {
        setCatalogKeywords(dedupe(topics.flatMap(t => t.keywords || [])));
        setCatalogConcepts(dedupe(topics.flatMap(t => t.key_concepts || [])));
        setCatalogCategories(dedupe(topics.flatMap(t => t.arxiv_categories || [])));
      })
      .catch(() => {
        // suggestions are a nicety, not a requirement — a failed fetch
        // just means the add-chip input has no dropdown, nothing breaks
      });
  }, []);

  const categorySuggestions = useMemo(
    () => dedupe([...catalogCategories, ...ARXIV_CATEGORIES]),
    [catalogCategories],
  );

  const canGenerate =
    title.trim().length > 0 &&
    description.trim().length >= MIN_DESCRIPTION_CHARS &&
    !generating;

  async function handleGenerate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError(null);
    try {
      const interests = `${title.trim()}\n\n${description.trim()}`;
      const result = await generateTopicDraft(interests);
      setKeywords(result.keywords);
      setCategories(result.arxiv_categories);
      setConcepts(result.key_concepts);
      setStage('review');
    } catch (e: any) {
      setError(e?.message || 'Could not generate a draft. Try again.');
    } finally {
      setGenerating(false);
    }
  }

  function handleStartOver() {
    setStage('input');
    setError(null);
  }

  async function handleCreate() {
    setCreating(true);
    setError(null);

    const name = title.trim();

    let topicId: string;
    try {
      const topic = await createTopic({
        name,
        keywords,
        arxiv_categories: categories,
        key_concepts: concepts,
        visibility,
      });
      topicId = topic.id;
    } catch (e: any) {
      setCreating(false);
      setError(e?.message || 'Could not create the topic. Nothing was saved — try again.');
      return;
    }

    try {
      const scope = await createScope({
        name,
        description: description.trim() || null,
        visibility,
        scope_mode: 'silo',
        scope_topic_ids: [topicId],
      });
      router.push(`/settings/scope/library?created=${encodeURIComponent(scope.name)}`);
    } catch (e: any) {
      setCreating(false);
      setError(
        (e?.message || 'Could not create the scope.') +
          ' The topic itself was saved to your catalog — you can wrap it in a scope from ' +
          '"New scope" without losing the generated keywords.',
      );
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-ink">Generate a scope</h1>
        <p className="text-ink-2 mt-1">
          Describe what you want to study. We'll draft the search keywords and arXiv
          categories for you — nothing is saved until you approve it.
        </p>
      </header>

      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {stage === 'input' ? (
        <section className="bg-paper-2 border border-rule rounded-lg p-5 space-y-4">
          <Field label="Title" htmlFor="gs-title" hint="Becomes the scope and topic name.">
            <input
              id="gs-title"
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              maxLength={200}
              placeholder="e.g. Diffusion models for protein design"
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
            />
          </Field>
          <Field
            label="Description"
            htmlFor="gs-description"
            hint="A sentence or two is enough — more detail makes for a better draft."
          >
            <textarea
              id="gs-description"
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="What do you want your daily papers to cover?"
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
            />
          </Field>
          <div className="flex items-center justify-between">
            <Link href="/topics/new" className="text-sm text-sky-700 hover:underline">
              Prefer to fill it in yourself? Use the manual form →
            </Link>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={!canGenerate}
              className="px-4 py-2 bg-gold-dark text-white rounded-lg text-sm font-medium hover:bg-[#734f14] disabled:opacity-50"
            >
              {generating ? 'Generating…' : 'Generate draft'}
            </button>
          </div>
        </section>
      ) : (
        <section className="bg-paper-2 border border-rule rounded-lg p-5 space-y-5">
          <div className="flex items-baseline justify-between gap-4 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
                Draft for &ldquo;{title.trim()}&rdquo;
              </h2>
              <p className="text-xs text-muted mt-1">
                Click a bubble to edit or delete it. Edit anything before approving —
                this is only saved once you create the scope.
              </p>
            </div>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || creating}
              className="text-sm px-3 py-1.5 bg-paper-3 text-ink-2 rounded hover:bg-rule disabled:opacity-50"
            >
              {generating ? 'Regenerating…' : 'Regenerate'}
            </button>
          </div>

          <Field label="Keywords">
            <ChipListEditor
              items={keywords}
              onChange={setKeywords}
              suggestions={catalogKeywords}
              addPlaceholder="Add a keyword…"
              emptyHint="No keywords yet — add at least a few for discovery to find papers."
            />
          </Field>

          <Field label="arXiv categories">
            <ChipListEditor
              items={categories}
              onChange={setCategories}
              suggestions={categorySuggestions}
              addPlaceholder="e.g. cs.LG"
              monospace
              emptyHint="Optional — leave empty if this topic isn't a natural arXiv fit."
            />
          </Field>

          <Field label="Key concepts">
            <ChipListEditor
              items={concepts}
              onChange={setConcepts}
              suggestions={catalogConcepts}
              addPlaceholder="Add a concept…"
              emptyHint="Foundational concepts a learner should understand."
            />
          </Field>

          <Field label="Visibility" htmlFor="gs-visibility">
            <select
              id="gs-visibility"
              value={visibility}
              onChange={e => setVisibility(e.target.value as ScopeVisibility)}
              className="px-3 py-2 border border-rule rounded text-sm bg-paper-2"
            >
              <option value="private">Private — only you</option>
              <option value="public">Public — discoverable by other users</option>
            </select>
          </Field>

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={handleStartOver}
              disabled={creating}
              className="text-sm text-muted hover:text-ink-2 underline disabled:opacity-50"
            >
              Start over
            </button>
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating || !title.trim()}
              className="px-4 py-2 bg-gold-dark text-white rounded-lg text-sm font-medium hover:bg-[#734f14] disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'Create scope'}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function Field({
  label, htmlFor, hint, children,
}: { label: string; htmlFor?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-sm font-medium text-ink-2">{label}</label>
        ) : (
          <span className="text-sm font-medium text-ink-2">{label}</span>
        )}
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
