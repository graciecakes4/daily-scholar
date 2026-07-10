'use client';

/**
 * /onboarding — three-step wizard for first-time users.
 *
 *   1. Describe your interests (free text) → Generate
 *   2. Review + edit the LLM-generated draft → Save and finish
 *   3. "You're all set" summary → links into the app
 *
 * Skip link on every step. Layout's OnboardingGuard redirects unonboarded
 * users here; once `onboarded=true` (via complete OR skip), the guard
 * stops bouncing them and the layout lets them through.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import {
  completeOnboarding,
  generateTopicDraft,
  skipOnboarding,
  type TopicDraft,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type Step = 'describe' | 'review' | 'done';

export default function OnboardingPage() {
  const router = useRouter();
  const { refresh } = useAuth();

  const [step, setStep] = useState<Step>('describe');
  const [interests, setInterests] = useState('');
  const [draft, setDraft] = useState<TopicDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form state for the review step (mirrors the draft so edits don't
  // mutate the original LLM output and we can "regenerate" if we add it later)
  const [editedName, setEditedName] = useState('');
  const [editedKeywords, setEditedKeywords] = useState('');
  const [editedCategories, setEditedCategories] = useState('');
  const [editedConcepts, setEditedConcepts] = useState('');
  const [visibility, setVisibility] = useState<'private' | 'public'>('private');

  async function onGenerate() {
    setBusy(true);
    setError(null);
    try {
      const d = await generateTopicDraft(interests);
      setDraft(d);
      // seed editable form
      setEditedName(d.name);
      setEditedKeywords(d.keywords.join('\n'));
      setEditedCategories(d.arxiv_categories.join('\n'));
      setEditedConcepts(d.key_concepts.join('\n'));
      setStep('review');
    } catch (e: any) {
      setError(e?.message || 'Generation failed');
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    setBusy(true);
    setError(null);
    try {
      await completeOnboarding({
        name: editedName.trim(),
        keywords: splitList(editedKeywords),
        arxiv_categories: splitList(editedCategories),
        key_concepts: splitList(editedConcepts),
        visibility,
      });
      await refresh();        // re-fetch /auth/me so onboarded=true takes effect
      setStep('done');
    } catch (e: any) {
      setError(e?.message || 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  async function onSkip() {
    setBusy(true);
    setError(null);
    try {
      await skipOnboarding();
      await refresh();
      router.push('/');
    } catch (e: any) {
      setError(e?.message || 'Skip failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto mt-8 space-y-6">
      <header>
        <h1 className="font-serif text-3xl font-bold text-ink">Welcome to Daily Scholar</h1>
        <p className="text-ink-2 mt-1">
          Let's set up your first topic. Daily Scholar uses topics to discover
          relevant papers, generate reviews, and build quizzes — tell us what
          you want to learn about and we'll draft one for you.
        </p>
      </header>

      <Steps current={step} />

      {error && (
        <div className="bg-rust/5 border border-rust/25 text-rust rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {step === 'describe' && (
        <section className="bg-paper-2 border border-rule rounded-lg p-6 space-y-4">
          <label className="block">
            <div className="text-sm font-medium text-ink-2 mb-1">
              What do you want to study?
            </div>
            <textarea
              value={interests}
              onChange={e => setInterests(e.target.value)}
              rows={5}
              placeholder="e.g. transformer architectures, attention mechanisms, and how they apply to vision-language models"
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm focus:outline-none focus:border-ink"
              autoFocus
            />
            <p className="text-xs text-muted mt-1">
              A sentence or two is enough. We'll extract keywords + arXiv categories you can edit.
            </p>
          </label>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={onSkip}
              disabled={busy}
              className="text-sm text-muted hover:text-ink-2 hover:underline disabled:opacity-50"
            >
              Skip for now
            </button>
            <button
              type="button"
              onClick={onGenerate}
              disabled={busy || interests.trim().length < 4}
              className="px-5 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14] disabled:opacity-50"
            >
              {busy ? 'Generating…' : 'Generate topic'}
            </button>
          </div>
        </section>
      )}

      {step === 'review' && draft !== null && (
        <section className="bg-paper-2 border border-rule rounded-lg p-6 space-y-4">
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">
            Review your topic
          </h2>
          <p className="text-sm text-ink-2">
            Edit anything that looks off. You can refine all of this later from <strong>Settings → Topics</strong>.
          </p>

          <Field label="Topic name">
            <input
              type="text"
              value={editedName}
              onChange={e => setEditedName(e.target.value)}
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm"
              required
            />
          </Field>

          <Field label="Keywords" hint="One per line — these drive paper discovery.">
            <textarea
              value={editedKeywords}
              onChange={e => setEditedKeywords(e.target.value)}
              rows={6}
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm font-mono"
            />
          </Field>

          <Field label="arXiv categories" hint="One per line — e.g. cs.LG, astro-ph.HE">
            <textarea
              value={editedCategories}
              onChange={e => setEditedCategories(e.target.value)}
              rows={3}
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm font-mono"
            />
          </Field>

          <Field label="Key concepts" hint="What does someone studying this topic need to understand?">
            <textarea
              value={editedConcepts}
              onChange={e => setEditedConcepts(e.target.value)}
              rows={5}
              className="bg-paper text-ink w-full px-3 py-2 border border-rule rounded text-sm"
            />
          </Field>

          <Field label="Visibility" hint={visibility === 'private' ? 'Only you can see this topic.' : 'Other users can subscribe via Discover.'}>
            <select
              value={visibility}
              onChange={e => setVisibility(e.target.value as 'private' | 'public')}
              className="bg-paper text-ink w-full max-w-xs px-3 py-2 border border-rule rounded text-sm"
            >
              <option value="private">Private</option>
              <option value="public">Public</option>
            </select>
          </Field>

          <div className="flex items-center justify-between pt-2">
            <button
              type="button"
              onClick={() => setStep('describe')}
              className="text-sm text-muted hover:text-ink-2 hover:underline"
            >
              ← Edit interests
            </button>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onSkip}
                disabled={busy}
                className="text-sm text-muted hover:text-ink-2 hover:underline disabled:opacity-50"
              >
                Skip
              </button>
              <button
                type="button"
                onClick={onSave}
                disabled={busy || !editedName.trim()}
                className="px-5 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14] disabled:opacity-50"
              >
                {busy ? 'Saving…' : 'Save topic + finish'}
              </button>
            </div>
          </div>
        </section>
      )}

      {step === 'done' && (
        <section className="bg-paper-2 border border-rule rounded-lg p-6 space-y-4 text-center">
          <div className="text-4xl">🎓</div>
          <h2 className="font-serif text-xl font-bold text-ink">You're all set</h2>
          <p className="text-sm text-ink-2">
            Your first topic is live. Here's what to explore next.
          </p>
          <div className="grid grid-cols-2 gap-3 pt-2">
            <NextStep href="/" title="Today's paper" hint="See what we found for you" />
            <NextStep href="/topics" title="My topics" hint="Tune keywords + add more" />
            <NextStep href="/quiz" title="Quiz" hint="Test what you know" />
            <NextStep href="/settings/notifications" title="Notifications" hint="Set study reminders" />
          </div>
          <div className="pt-2">
            <Link
              href="/"
              className="inline-block px-5 py-2 bg-gold-dark text-white rounded font-medium hover:bg-[#734f14]"
            >
              Go to dashboard
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}

// ---------- shared bits ----------

function Steps({ current }: { current: Step }) {
  const order: Step[] = ['describe', 'review', 'done'];
  const labels: Record<Step, string> = {
    describe: 'Describe',
    review: 'Review',
    done: 'Done',
  };
  return (
    <ol className="flex items-center gap-2 text-xs text-muted">
      {order.map((s, i) => {
        const active = s === current;
        const past = order.indexOf(current) > i;
        return (
          <li key={s} className="flex items-center gap-2">
            <span
              className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold ${
                active
                  ? 'bg-gold-dark text-white'
                  : past
                    ? 'bg-moss text-white'
                    : 'bg-rule text-ink-2'
              }`}
            >
              {past ? '✓' : i + 1}
            </span>
            <span className={active ? 'text-ink font-medium' : ''}>{labels[s]}</span>
            {i < order.length - 1 && <span className="text-muted">→</span>}
          </li>
        );
      })}
    </ol>
  );
}

function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-ink-2">{label}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

function NextStep({ href, title, hint }: { href: string; title: string; hint: string }) {
  return (
    <Link
      href={href}
      className="block bg-paper hover:bg-paper-3 border border-rule rounded p-3 text-left"
    >
      <div className="font-medium text-ink text-sm">{title} →</div>
      <div className="text-xs text-muted mt-0.5">{hint}</div>
    </Link>
  );
}

function splitList(s: string): string[] {
  return s
    .split(/[\n,]/)
    .map(x => x.trim())
    .filter(Boolean);
}
