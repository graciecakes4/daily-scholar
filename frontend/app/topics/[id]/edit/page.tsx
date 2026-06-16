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
        <Link href="/topics" className="text-sm text-slate-500 hover:text-slate-700">← back to topics</Link>
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-lg px-4 py-3">{error}</div>
      </div>
    );
  }

  if (!topic) {
    return <div className="text-slate-500">Loading…</div>;
  }

  return (
    <div className="space-y-6">
      <header>
        <Link href="/topics" className="text-sm text-slate-500 hover:text-slate-700">← back to topics</Link>
        <h1 className="text-3xl font-bold text-slate-900 mt-2">{topic.name}</h1>
        <p className="text-slate-600 mt-1">
          Editing topic <code className="text-sm">{topic.id}</code>
          {topic.created_via === 'yaml' && (
            <span className="ml-2 text-xs px-2 py-0.5 bg-amber-100 text-amber-800 rounded">
              Originally from YAML — DB-wins on next reload
            </span>
          )}
        </p>
      </header>
      <TopicForm mode="edit" initial={topic} />
    </div>
  );
}
