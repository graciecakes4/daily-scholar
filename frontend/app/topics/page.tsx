'use client';

import { useState, useEffect } from 'react';

interface ArchivedTopic {
  id: number;
  topic_id: string;
  topic_name: string;
  course_id: string;
  course_name: string;
  review_count: number;
  confidence_level?: number;
  user_notes?: string;
  first_reviewed_at: string;
  last_reviewed_at: string;
}

export default function TopicsPage() {
  const [topics, setTopics] = useState<ArchivedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ unique_topics: 0, total_reviews: 0 });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [topicsRes, statsRes] = await Promise.all([
        fetch('http://localhost:8000/archive/topics'),
        fetch('http://localhost:8000/archive/stats'),
      ]);
      const topicsData = await topicsRes.json();
      const statsData = await statsRes.json();
      setTopics(topicsData.topics || []);
      setStats(statsData.topics || { unique_topics: 0, total_reviews: 0 });
    } catch (error) {
      console.error('Failed to fetch:', error);
    } finally {
      setLoading(false);
    }
  };

  const deleteTopic = async (id: number) => {
    if (!confirm('Delete this topic from your archive?')) return;
    await fetch(`http://localhost:8000/archive/topics/${id}`, { method: 'DELETE' });
    fetchData();
  };

  const ConfidenceBadge = ({ level }: { level?: number }) => {
    if (!level) return null;
    const colors = ['', 'bg-red-100 text-red-700', 'bg-orange-100 text-orange-700', 'bg-yellow-100 text-yellow-700', 'bg-lime-100 text-lime-700', 'bg-emerald-100 text-emerald-700'];
    const labels = ['', 'Struggling', 'Needs Work', 'Getting There', 'Good', 'Mastered'];
    return <span className={`px-2 py-1 text-xs font-medium rounded ${colors[level]}`}>{labels[level]}</span>;
  };

  if (loading) {
    return <div className="flex justify-center py-20"><div className="animate-pulse text-slate-500">Loading...</div></div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">🧠 Topic Reviews</h1>
          <p className="text-slate-600 mt-1">{stats.unique_topics} topics • {stats.total_reviews} total reviews</p>
        </div>
        <a href="/" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          ← Back to Dashboard
        </a>
      </div>

      {topics.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-slate-700 mb-2">No Topics Reviewed Yet</h2>
          <p className="text-slate-500">Complete topic reviews to build your study archive.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {topics.map((topic) => (
            <div key={topic.id} className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg transition-all">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-xs font-medium rounded">
                      {topic.course_name}
                    </span>
                    <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                      Week {topic.week_covered || '?'}
                    </span>
                    <ConfidenceBadge level={topic.confidence_level} />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-1">{topic.topic_name}</h3>
                  <div className="flex items-center gap-4 text-sm text-slate-500">
                    <span>📖 Reviewed {topic.review_count} time{topic.review_count !== 1 ? 's' : ''}</span>
                    <span>Last: {new Date(topic.last_reviewed_at).toLocaleDateString()}</span>
                  </div>
                  {topic.user_notes && (
                    <p className="mt-2 text-sm text-slate-600 bg-slate-50 p-2 rounded">
                      📝 {topic.user_notes}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <a href={`/?topic=${topic.topic_id}`}
                     className="px-3 py-1 text-sm bg-emerald-100 text-emerald-700 rounded hover:bg-emerald-200">
                    Review Again
                  </a>
                  <button onClick={() => deleteTopic(topic.id)}
                          className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
