'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import TopicForm from '@/components/TopicForm';
import { getTopic, type Topic } from '@/lib/api';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function EditTopicPage({ params }: PageProps) {
  const { id } = use(params);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setTopic(await getTopic(id));
      } catch (e: any) {
        setError(e.message);
      }
    })();
  }, [id]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/topics" className="text-sm text-muted hover:text-ink-2">← back to topics</Link>
        <div className="bg-rust/5 border border-rust/25 text-rust rounded-lg px-4 py-3">{error}</div>
      </div>
    );
  }

  if (!topic) {
    return <div className="text-muted">Loading…</div>;
  }

  return (
    <div className="space-y-6">
      <header>
        <Link href="/topics" className="text-sm text-muted hover:text-ink-2">← back to topics</Link>
        <h1 className="text-3xl font-bold text-ink mt-2">{topic.name}</h1>
        <p className="text-ink-2 mt-1">
          Editing topic <code className="text-sm">{topic.id}</code>
          {topic.created_via === 'yaml' && (
            <span className="ml-2 text-xs px-2 py-0.5 bg-gold/10 text-gold-dark rounded">
              Originally from YAML — DB-wins on next reload
            </span>
          )}
        </p>
      </header>
      <TopicForm mode="edit" initial={topic} />
    </div>
  );
}
