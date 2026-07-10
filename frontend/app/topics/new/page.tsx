'use client';

import Link from 'next/link';
import TopicForm from '@/components/TopicForm';

export default function NewTopicPage() {
  return (
    <div className="space-y-6">
      <header>
        <Link href="/topics" className="text-sm text-muted hover:text-ink-2">← back to topics</Link>
        <h1 className="font-serif text-3xl font-bold text-ink mt-2">New topic</h1>
        <p className="text-ink-2 mt-1">
          UI-created topics live only in the database until you export them. Use the Export DB → YAML button on the topics list to write them to <code>config/topics/</code>.
        </p>
      </header>
      <TopicForm mode="create" />
    </div>
  );
}
