'use client';
// TODO: add topic reset buttons //
import { useState, useEffect } from 'react';
import {
  getArchivedTopics, updateArchivedTopic, deleteArchivedTopic,
  type ArchivedTopic
} from '@/lib/api';

export default function TopicsPage() {
  const [topics, setTopics] = useState<ArchivedTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editingNotes, setEditingNotes] = useState<number | null>(null);
  const [noteText, setNoteText] = useState('');

  useEffect(() => {
    fetchTopics();
  }, []);

  const fetchTopics = async () => {
    setLoading(true);
    try {
      const data = await getArchivedTopics(50, 0);
      setTopics(data.topics);
    } catch (error) {
      console.error('Failed to fetch topics:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConfidenceChange = async (topicId: number, level: number) => {
    try {
      await updateArchivedTopic(topicId, { confidence_level: level });
      fetchTopics();
    } catch (error) {
      console.error('Failed to update confidence:', error);
    }
  };

  const handleSaveNotes = async (topicId: number) => {
    try {
      await updateArchivedTopic(topicId, { user_notes: noteText });
      setEditingNotes(null);
      fetchTopics();
    } catch (error) {
      console.error('Failed to save notes:', error);
    }
  };

  const handleDelete = async (topicId: number) => {
    if (!confirm('Remove this topic from your archive?')) return;
    try {
      await deleteArchivedTopic(topicId);
      fetchTopics();
    } catch (error) {
      console.error('Failed to delete topic:', error);
    }
  };

  const ConfidenceLevel = ({ level, topicId }: { level: number; topicId: number }) => {
    const labels = ['Not set', 'Struggling', 'Needs Work', 'Getting There', 'Confident', 'Mastered'];
    const colors = [
      'bg-slate-100 text-slate-600',
      'bg-red-100 text-red-700',
      'bg-orange-100 text-orange-700',
      'bg-yellow-100 text-yellow-700',
      'bg-emerald-100 text-emerald-700',
      'bg-blue-100 text-blue-700',
    ];

    return (
      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => handleConfidenceChange(topicId, n)}
              className={`w-8 h-8 rounded-full text-sm font-medium transition-all ${n <= level
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-200 text-slate-500 hover:bg-slate-300'
                }`}
            >
              {n}
            </button>
          ))}
        </div>
        <span className={`px-2 py-1 text-xs rounded ${colors[level] || colors[0]}`}>
          {labels[level] || labels[0]}
        </span>
      </div>
    );
  };

  // Group topics by course
  const topicsByCourse = topics.reduce((acc, topic) => {
    if (!acc[topic.course_name]) {
      acc[topic.course_name] = [];
    }
    acc[topic.course_name].push(topic);
    return acc;
  }, {} as Record<string, ArchivedTopic[]>);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="animate-pulse text-slate-500">Loading topics...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">🧠 Topic Reviews</h1>
          <p className="text-slate-600 mt-1">
            {topics.length} topics reviewed • {topics.reduce((sum, t) => sum + t.review_count, 0)} total reviews
          </p>
        </div>
        <a href="/" className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200">
          ← Dashboard
        </a>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-slate-900">{topics.length}</div>
          <div className="text-sm text-slate-500">Unique Topics</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-emerald-600">
            {topics.filter(t => (t.confidence_level || 0) >= 4).length}
          </div>
          <div className="text-sm text-slate-500">Confident</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-amber-600">
            {topics.filter(t => (t.confidence_level || 0) > 0 && (t.confidence_level || 0) < 4).length}
          </div>
          <div className="text-sm text-slate-500">Needs Practice</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-2xl font-bold text-slate-400">
            {topics.filter(t => !t.confidence_level).length}
          </div>
          <div className="text-sm text-slate-500">Not Rated</div>
        </div>
      </div>

      {/* Topics by Course */}
      {topics.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
          <h2 className="text-xl font-semibold text-slate-700 mb-2">No Topics Reviewed Yet</h2>
          <p className="text-slate-500">Complete topic reviews from your daily learning to track your progress.</p>
        </div>
      ) : (
        Object.entries(topicsByCourse).map(([courseName, courseTopics]) => (
          <div key={courseName} className="space-y-4">
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
              {courseName}
              <span className="text-sm font-normal text-slate-500">({courseTopics.length} topics)</span>
            </h2>

            <div className="space-y-3">
              {courseTopics.map((topic) => (
                <div key={topic.id} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-semibold text-slate-900">{topic.topic_name}</h3>
                          <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded">
                            Week {topic.week_covered}
                          </span>
                          <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">
                            {topic.review_count}x reviewed
                          </span>
                        </div>

                        <ConfidenceLevel level={topic.confidence_level || 0} topicId={topic.id} />

                        <p className="text-xs text-slate-400 mt-2">
                          Last reviewed: {new Date(topic.last_reviewed_at).toLocaleDateString()}
                        </p>
                      </div>

                      <button
                        onClick={() => setExpandedId(expandedId === topic.id ? null : topic.id)}
                        className="p-2 text-slate-400 hover:text-slate-600"
                      >
                        <svg className={`w-5 h-5 transition-transform ${expandedId === topic.id ? 'rotate-180' : ''}`}
                          fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </div>

                    {/* Expanded Content */}
                    {expandedId === topic.id && (
                      <div className="mt-4 pt-4 border-t border-slate-100 space-y-4">
                        {topic.key_points && topic.key_points.length > 0 && (
                          <div className="bg-emerald-50 rounded-lg p-4">
                            <h4 className="font-semibold text-emerald-900 mb-2">Key Points</h4>
                            <ul className="space-y-1">
                              {topic.key_points.map((point: string, i: number) => (
                                <li key={i} className="text-sm text-emerald-800 flex items-start gap-2">
                                  <span className="text-emerald-500">✓</span>
                                  {point}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Notes Section */}
                        <div className="bg-slate-50 rounded-lg p-4">
                          <div className="flex items-center justify-between mb-2">
                            <h4 className="font-semibold text-slate-900">Your Notes</h4>
                            {editingNotes !== topic.id && (
                              <button
                                onClick={() => {
                                  setEditingNotes(topic.id);
                                  setNoteText(topic.user_notes || '');
                                }}
                                className="text-sm text-blue-600 hover:text-blue-700"
                              >
                                {topic.user_notes ? 'Edit' : 'Add notes'}
                              </button>
                            )}
                          </div>

                          {editingNotes === topic.id ? (
                            <div className="space-y-2">
                              <textarea
                                value={noteText}
                                onChange={(e) => setNoteText(e.target.value)}
                                placeholder="Add your notes about this topic..."
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm resize-none h-24 focus:ring-2 focus:ring-blue-500"
                              />
                              <div className="flex gap-2">
                                <button
                                  onClick={() => handleSaveNotes(topic.id)}
                                  className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                                >
                                  Save
                                </button>
                                <button
                                  onClick={() => setEditingNotes(null)}
                                  className="px-3 py-1.5 bg-slate-200 text-slate-700 text-sm rounded hover:bg-slate-300"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm text-slate-600">
                              {topic.user_notes || 'No notes yet.'}
                            </p>
                          )}
                        </div>

                        <div className="flex justify-end">
                          <button
                            onClick={() => handleDelete(topic.id)}
                            className="px-3 py-1.5 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                          >
                            Remove from Archive
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
