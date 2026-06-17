'use client';

import Link from 'next/link';
import TopicForm from '@/components/TopicForm';

export default function NewTopicPage() {
  return (
    <div className="space-y-6">
      <header>
        <Link href="/topics" className="text-sm text-slate-500 hover:text-slate-700">← back to topics</Link>
        <h1 className="text-3xl font-bold text-slate-900 mt-2">New topic</h1>
        <p className="text-slate-600 mt-1">
          UI-created topics live only in the database until you export them. Use the Export DB → YAML button on the topics list to write them to <code>config/topics/</code>.
        </p>
      </header>
      <TopicForm mode="create" />
    </div>
  );
}
